"""Fetch detail pages in the background after a report list is saved."""

import threading
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import close_old_connections, transaction

from dashboard.models import ReportDetail, ReportSnapshot
from dashboard.services.wildberries import (
    RateLimitError,
    WildberriesError,
    fetch_deduction_page,
)

_active = set()
_lock = threading.Lock()


def start_detail_worker(snapshot_id):
    with _lock:
        if snapshot_id in _active:
            return
        _active.add(snapshot_id)
    threading.Thread(target=_run, args=(snapshot_id,), daemon=True).start()


def _run(snapshot_id):
    close_old_connections()
    try:
        initial = ReportSnapshot.objects.get(pk=snapshot_id)
        if initial.detail_cursor == 0:
            report_ids = [str(report['reportId']) for report in initial.reports]
            ReportDetail.objects.filter(
                report_id__in=report_ids, complete=False
            ).update(entries=[])
        while True:
            snapshot = ReportSnapshot.objects.get(pk=snapshot_id)
            if snapshot.detail_complete or snapshot.detail_error:
                return
            try:
                page = fetch_deduction_page(
                    snapshot.date_from, snapshot.date_to,
                    snapshot.period, snapshot.detail_cursor,
                )
            except RateLimitError:
                time.sleep(65)
                continue
            except WildberriesError as exc:
                snapshot.detail_error = str(exc)
                snapshot.save(update_fields=['detail_error'])
                return

            report_ids = [str(report['reportId']) for report in snapshot.reports]
            if page is None:
                with transaction.atomic():
                    ReportDetail.objects.filter(report_id__in=report_ids).update(complete=True)
                    snapshot.detail_complete = True
                    snapshot.save(update_fields=['detail_complete'])
                return

            grouped = defaultdict(list)
            for row in page:
                report_id = str(row['reportId'])
                if report_id not in report_ids:
                    continue
                try:
                    amount = Decimal(str(row.get('deduction') or '0'))
                except (InvalidOperation, TypeError, ValueError):
                    continue
                if amount:
                    grouped[report_id].append({
                        'amount': str(amount),
                        'reason': row.get('bonusTypeName') or row.get('sellerOperName')
                                  or 'Без указания причины',
                    })

            with transaction.atomic():
                for report_id, entries in grouped.items():
                    detail, _ = ReportDetail.objects.get_or_create(report_id=report_id)
                    if not detail.complete:
                        detail.entries = detail.entries + entries
                        detail.save(update_fields=['entries', 'updated_at'])
                snapshot.detail_cursor = page[-1]['rrdId']
                snapshot.save(update_fields=['detail_cursor'])
            time.sleep(65)
    except Exception:
        # Leave a readable status; a new list import can retry from the beginning.
        ReportSnapshot.objects.filter(pk=snapshot_id).update(
            detail_error='Не удалось завершить загрузку детализации. Загрузите отчёты повторно.'
        )
    finally:
        close_old_connections()
        with _lock:
            _active.discard(snapshot_id)
