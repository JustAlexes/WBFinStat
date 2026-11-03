import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.forms import ReportPeriodForm
from dashboard.models import ReportDetail, ReportSnapshot
from dashboard.services.wildberries import (
    WildberriesError, fetch_deduction_page, fetch_report_list, get_token,
)

MONEY_FIELDS = (
    ('retailAmountSum', 'Сумма продаж по отчёту'),
    ('forPaySum', 'К перечислению за товар'),
    ('deliveryServiceSum', 'Логистика'),
    ('paidStorageSum', 'Платное хранение'),
    ('paidAcceptanceSum', 'Платная приёмка'),
    ('deductionSum', 'Удержания'),
    ('penaltySum', 'Штрафы'),
    ('additionalPaymentSum', 'Доплаты'),
    ('bankPaymentSum', 'Банковский платёж'),
)


def money(value):
    try:
        return f'{Decimal(str(value)):,.2f}'.replace(',', ' ')
    except (InvalidOperation, TypeError, ValueError):
        return '—'


def report_context(snapshot):
    if snapshot is None:
        return {'report_count': 0, 'summaries': [], 'report_rows': []}

    totals = defaultdict(lambda: defaultdict(Decimal))
    rows = []
    details = {
        item.report_id: item
        for item in ReportDetail.objects.filter(
            report_id__in=[str(report.get('reportId')) for report in snapshot.reports]
        )
    }
    for report in snapshot.reports:
        currency = report.get('currency') or '—'
        report_id = str(report.get('reportId', '—'))
        detail = details.get(report_id)
        for key, _label in MONEY_FIELDS:
            value = report.get(key)
            if value is not None:
                try:
                    totals[currency][key] += Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError):
                    pass
        rows.append({
            'id': report_id,
            'from': report.get('dateFrom', '—'),
            'to': report.get('dateTo', '—'),
            'type': report.get('reportType', '—'),
            'currency': currency,
            'for_pay': money(report.get('forPaySum')),
            'delivery': money(report.get('deliveryServiceSum')),
            'sold': money(report.get('retailAmountSum')),
            'storage': money(report.get('paidStorageSum')),
            'deduction': money(report.get('deductionSum')),
            'penalty': money(report.get('penaltySum')),
            'detail': detail,
            'detail_rows': [
                {**entry, 'formatted_amount': money(entry['amount'])}
                for entry in detail.entries
            ] if detail else [],
            'detail_sum': money(sum(
                (Decimal(str(entry['amount'])) for entry in detail.entries),
                Decimal('0'),
            )) if detail and detail.complete else None,
            'detail_matches': (
                sum((Decimal(str(entry['amount'])) for entry in detail.entries), Decimal('0'))
                == Decimal(str(report.get('deductionSum')))
            ) if detail and detail.complete and report.get('deductionSum') is not None else None,
            'raw': json.dumps(report, ensure_ascii=False, indent=2),
        })

    summaries = [
        {
            'currency': currency,
            'values': [
                {'label': label, 'amount': money(amounts[key])}
                for key, label in MONEY_FIELDS if key in amounts
            ],
        }
        for currency, amounts in sorted(totals.items())
    ]
    return {
        'report_count': len(rows),
        'summaries': summaries,
        'report_rows': rows,
    }


@require_http_methods(['GET', 'POST'])
def home(request):
    today = timezone.localdate()
    initial = {
        'date_from': today - timedelta(days=30),
        'date_to': today,
        'period': 'weekly',
    }
    form = ReportPeriodForm(request.POST or None, initial=initial)
    snapshot = ReportSnapshot.objects.first()
    success = None
    error = None

    if request.method == 'POST' and form.is_valid():
        try:
            data = form.cleaned_data
            reports = fetch_report_list(
                data['date_from'], data['date_to'], data['period']
            )
            snapshot = ReportSnapshot.objects.create(
                date_from=data['date_from'],
                date_to=data['date_to'],
                period=data['period'],
                reports=reports,
            )
            success = f'Загружено отчётов: {len(reports)}.'
        except WildberriesError as exc:
            error = str(exc)

    context = {
        'form': form,
        'snapshot': snapshot,
        'success': success,
        'error': error,
        'token_configured': bool(get_token()),
        **report_context(snapshot),
    }
    return render(request, 'dashboard/home.html', context)


@require_POST
def load_deductions(request, report_id):
    snapshot = ReportSnapshot.objects.first()
    if snapshot is None or not any(
        str(item.get('reportId')) == str(report_id) for item in snapshot.reports
    ):
        raise Http404('Отчёт не найден в последней загрузке.')
    detail, _ = ReportDetail.objects.get_or_create(report_id=str(report_id))
    if not detail.complete:
        try:
            page = fetch_deduction_page(report_id, detail.cursor)
            if page is None:
                detail.complete = True
            else:
                detail.cursor = page[-1]['rrdId']
                for row in page:
                    try:
                        amount = Decimal(str(row.get('deduction') or '0'))
                    except (InvalidOperation, ValueError):
                        continue
                    if amount:
                        detail.entries.append({
                            'amount': str(amount),
                            'reason': row.get('bonusTypeName') or row.get('sellerOperName') or 'Без указания причины',
                            'date': row.get('rrDate') or '—',
                        })
            detail.save()
            messages.success(request, 'Детализация обновлена. Для подтверждения полноты данных продолжайте до ответа «Загрузка завершена».')
        except WildberriesError as exc:
            messages.error(request, str(exc))
    return redirect(f'/?detail={report_id}#report-{report_id}')


def profile(request):
    return render(request, 'dashboard/profile.html')


def settings(request):
    return render(request, 'dashboard/settings.html')
