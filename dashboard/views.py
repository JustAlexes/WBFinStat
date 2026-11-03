import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from dashboard.forms import ReportPeriodForm
from dashboard.models import ReportSnapshot
from dashboard.services.wildberries import WildberriesError, fetch_report_list, get_token

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
    for report in snapshot.reports:
        currency = report.get('currency') or '—'
        for key, _label in MONEY_FIELDS:
            value = report.get(key)
            if value is not None:
                try:
                    totals[currency][key] += Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError):
                    pass
        rows.append({
            'id': report.get('reportId', '—'),
            'from': report.get('dateFrom', '—'),
            'to': report.get('dateTo', '—'),
            'type': report.get('reportType', '—'),
            'currency': currency,
            'for_pay': money(report.get('forPaySum')),
            'delivery': money(report.get('deliveryServiceSum')),
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


def profile(request):
    return render(request, 'dashboard/profile.html')


def settings(request):
    return render(request, 'dashboard/settings.html')
