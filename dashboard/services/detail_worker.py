"""Load and cache the deduction rows of each report in the background."""

import threading
import time
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


def _amount(value):
    try:
        return Decimal(str(value or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def prepare_details(snapshot):
    """Reuse valid caches and repair incomplete legacy period-based results."""
    pending = False
    for report in snapshot.reports:
        report_id = str(report['reportId'])
        expected = _amount(report.get('deductionSum'))
        detail, _ = ReportDetail.objects.get_or_create(report_id=report_id)
        if not expected:
            # No detailed API call is needed for an explicitly zero total.
            if report.get('deductionSum') is not None and (
                not detail.complete or detail.entries
            ):
                detail.entries = []
                detail.cursor = 0
                detail.complete = True
                detail.source = 'report'
                detail.save(update_fields=['entries', 'cursor', 'complete', 'source', 'updated_at'])
        elif detail.source != 'report':
            cached_total = sum((_amount(entry.get('amount')) for entry in detail.entries), Decimal('0'))
            if not detail.complete or cached_total != expected:
                detail.entries = []
                detail.cursor = 0
                detail.complete = False
            detail.source = 'report'
            detail.save(update_fields=['entries', 'cursor', 'complete', 'source', 'updated_at'])
        if not detail.complete:
            pending = True

    complete = not pending
    if snapshot.detail_complete != complete:
        snapshot.detail_complete = complete
        snapshot.save(update_fields=['detail_complete'])
    return complete


def start_detail_worker(snapshot_id):
    with _lock:
        if snapshot_id in _active:
            return
        _active.add(snapshot_id)
    threading.Thread(target=_run, args=(snapshot_id,), daemon=True).start()


def _run(snapshot_id):
    close_old_connections()
    try:
        snapshot = ReportSnapshot.objects.get(pk=snapshot_id)
        prepare_details(snapshot)
        report_ids = [str(report['reportId']) for report in snapshot.reports]
        while True:
            snapshot.refresh_from_db()
            if snapshot.detail_complete or snapshot.detail_error:
                return
            detail = ReportDetail.objects.filter(
                report_id__in=report_ids, complete=False
            ).first()
            if detail is None:
                snapshot.detail_complete = True
                snapshot.save(update_fields=['detail_complete'])
                return
            try:
                page = fetch_deduction_page(detail.report_id, detail.cursor)
            except RateLimitError:
                time.sleep(65)
                continue
            except WildberriesError as exc:
                snapshot.detail_error = str(exc)
                snapshot.save(update_fields=['detail_error'])
                return

            if page is None:
                detail.complete = True
                detail.save(update_fields=['complete', 'updated_at'])
                if ReportDetail.objects.filter(report_id__in=report_ids, complete=False).exists():
                    time.sleep(65)
                continue

            entries = []
            for row in page:
                if str(row['reportId']) != detail.report_id:
                    raise WildberriesError('Детализация содержит строку другого отчёта.')
                amount = _amount(row.get('deduction'))
                if amount:
                    entries.append({
                        'amount': str(amount),
                        'reason': row.get('bonusTypeName') or row.get('sellerOperName')
                                  or 'Без указания причины',
                    })

            with transaction.atomic():
                detail.entries = detail.entries + entries
                detail.cursor = int(page[-1]['rrdId'])
                detail.save(update_fields=['entries', 'cursor', 'updated_at'])
            time.sleep(65)
    except Exception:
        ReportSnapshot.objects.filter(pk=snapshot_id).update(
            detail_error='Не удалось завершить загрузку детализации. Загрузите отчёты повторно.'
        )
    finally:
        close_old_connections()
        with _lock:
            _active.discard(snapshot_id)
