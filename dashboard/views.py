from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache

from dashboard.forms import ReportPeriodForm
from dashboard.models import ReportDetail, ReportSnapshot
from dashboard.services.detail_worker import prepare_details, start_detail_worker
from dashboard.services.wildberries import WildberriesError, fetch_report_list, get_token

MONEY_FIELDS = (
    ('retailAmountSum', 'Сумма продаж по отчёту'),
    ('forPaySum', 'К перечислению за товар'),
    ('deliveryServiceSum', 'Логистика'),
    ('paidStorageSum', 'Платное хранение'),
    ('paidAcceptanceSum', 'Платная приёмка'),
    ('deductionSum', 'Удержания'),
    ('penaltySum', 'Штрафы'),
    ('additionalPaymentSum', 'Корректировка Вознаграждения Вайлдберриз'),
    ('cashbackDiscountSum', 'Компенсация скидки по программе лояльности'),
    ('cashbackCommissionChangeSum', 'Стоимость участия в программе лояльности'),
    ('cashbackAmountSum', 'Сумма баллов, удержанных по программе лояльности'),
    ('paymentSchedule', 'Изменение срока перечисления денежных средств'),
    ('bankPaymentSum', 'Итого к оплате'),
)


def money(value):
    try:
        return f'{Decimal(str(value)):,.2f}'.replace(',', ' ')
    except (InvalidOperation, TypeError, ValueError):
        return '—'


def display_date(value):
    if not value:
        return '—'
    try:
        return date.fromisoformat(str(value)[:10]).strftime('%d.%m.%Y')
    except ValueError:
        return str(value)


def report_type_label(value):
    if value is None:
        return '—'
    return {'1': 'Основной', '2': 'По выкупам'}.get(str(value), f'Тип {value}')


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

        grouped = defaultdict(Decimal)
        if detail:
            for entry in detail.entries:
                grouped[entry['reason']] += Decimal(str(entry['amount']))
        detail_rows = [
            {'reason': reason, 'formatted_amount': money(amount)}
            for reason, amount in sorted(grouped.items())
        ]
        detail_sum = sum(grouped.values(), Decimal('0'))
        expected = report.get('deductionSum')
        rows.append({
            'id': report_id,
            'from': display_date(report.get('dateFrom')),
            'to': display_date(report.get('dateTo')),
            'type': report_type_label(report.get('reportType')),
            'currency': currency,
            'for_pay': money(report.get('forPaySum')),
            'delivery': money(report.get('deliveryServiceSum')),
            'sold': money(report.get('retailAmountSum')),
            'storage': money(report.get('paidStorageSum')),
            'deduction': money(expected),
            'penalty': money(report.get('penaltySum')),
            'loyalty_compensation': money(report.get('cashbackDiscountSum')),
            'reward_adjustment': money(report.get('additionalPaymentSum')),
            'loyalty_fee': money(report.get('cashbackCommissionChangeSum')),
            'loyalty_points': money(report.get('cashbackAmountSum')),
            'payment_schedule': money(report.get('paymentSchedule')),
            'total_to_pay': money(report.get('bankPaymentSum')),
            'detail_rows': detail_rows if detail and detail.complete else [],
            'detail_complete': bool(detail and detail.complete),
            'detail_matches': (
                detail_sum == Decimal(str(expected))
            ) if detail and detail.complete and expected is not None else None,
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


@never_cache
@require_http_methods(['GET', 'POST'])
def home(request):
    snapshot = None
    if request.method == 'GET':
        snapshot_id = request.session.pop('report_result_id', None)
        if snapshot_id is not None:
            snapshot = ReportSnapshot.objects.filter(pk=snapshot_id).first()
    today = timezone.localdate()
    initial = {'date_from': snapshot.date_from, 'date_to': snapshot.date_to} if snapshot else {}
    form = ReportPeriodForm(request.POST or None, initial=initial)
    error = None

    if request.method == 'POST' and form.is_valid():
        try:
            data = form.cleaned_data
            reports = fetch_report_list(
                data['date_from'], data['date_to'], 'weekly'
            )
            snapshot = ReportSnapshot.objects.create(
                date_from=data['date_from'],
                date_to=data['date_to'],
                period='weekly',
                reports=reports,
            )
            complete = prepare_details(snapshot)
            if not complete:
                start_detail_worker(snapshot.pk)
            message = f'Загружено отчётов: {len(reports)}.'
            if not complete:
                message += ' Детализация подгружается автоматически.'
            messages.success(request, message)
            request.session['report_result_id'] = snapshot.pk
            return redirect(reverse('home'))
        except WildberriesError as exc:
            error = str(exc)

    if snapshot:
        prepare_details(snapshot)
        if not snapshot.detail_complete and not snapshot.detail_error:
            start_detail_worker(snapshot.pk)

    context = {
        'form': form,
        'snapshot': snapshot,
        'error': error,
        'token_configured': bool(get_token()),
        'calendar_today': today.isoformat(),
        **report_context(snapshot),
    }
    return render(request, 'dashboard/home.html', context)


@require_GET
def report_status(request, snapshot_id):
    snapshot = ReportSnapshot.objects.filter(pk=snapshot_id).first()
    if snapshot is None:
        return JsonResponse({'error': 'Отчёт не найден'}, status=404)
    if not snapshot.detail_complete and not snapshot.detail_error:
        start_detail_worker(snapshot.pk)
    result = {
        'complete': snapshot.detail_complete,
        'error': snapshot.detail_error,
    }
    if snapshot.detail_complete or snapshot.detail_error:
        result['html'] = render_to_string('dashboard/report_results.html', {
            'snapshot': snapshot, **report_context(snapshot),
        }, request=request)
    return JsonResponse(result)


def profile(request):
    return render(request, 'dashboard/profile.html')


def settings(request):
    return render(request, 'dashboard/settings.html')
