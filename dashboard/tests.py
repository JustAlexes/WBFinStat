from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase

from dashboard.forms import ReportPeriodForm
from dashboard.models import ReportDetail, ReportSnapshot
from dashboard.services.detail_worker import _run
from dashboard.services.wildberries import (
    RateLimitError,
    WildberriesError,
    fetch_deduction_page,
    fetch_report_list,
)


class WildberriesReportTests(TestCase):
    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.views.fetch_report_list')
    def test_landing_page_does_not_show_or_fetch_previous_reports(self, fetch, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
            detail_error='Не удалось загрузить детализацию Wildberries.',
        )
        page = self.client.get('/')
        self.assertIsNone(page.context['snapshot'])
        self.assertEqual(page.context['report_rows'], [])
        self.assertContains(page, 'Выберите период отчётов')
        self.assertNotContains(page, 'Не удалось загрузить детализацию')
        self.assertNotContains(page, '835092276')
        self.assertNotContains(page, 'data-status-url')
        self.assertTrue(ReportSnapshot.objects.filter(pk=snapshot.pk).exists())
        fetch.assert_not_called()
        worker.assert_not_called()

    @patch('dashboard.views.start_detail_worker')
    def test_landing_page_does_not_resume_pending_details(self, worker):
        ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
        )
        self.client.get('/')
        worker.assert_not_called()
        self.assertFalse(ReportDetail.objects.exists())

    @patch('dashboard.views.start_detail_worker')
    def test_report_columns_use_summary_fields(self, _worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{
                'reportId': 835092276,
                'dateFrom': '2026-10-19',
                'dateTo': '2026-10-25',
                'reportType': 1,
                'currency': 'RUB',
                'retailAmountSum': '1075580',
                'paidStorageSum': '743.99',
                'deductionSum': '154330',
                'penaltySum': '160',
                'cashbackDiscountSum': '2571.93',
                'additionalPaymentSum': '0',
                'cashbackCommissionChangeSum': '47.71',
                'cashbackAmountSum': '350',
                'paymentSchedule': '0',
                'bankPaymentSum': '514684.5',
            }],
        )
        page = self.client.get(f'/?snapshot={snapshot.pk}')
        row = page.context['report_rows'][0]
        self.assertEqual(row['sold'], '1 075 580.00')
        self.assertEqual(row['storage'], '743.99')
        self.assertEqual(row['deduction'], '154 330.00')
        self.assertEqual(row['penalty'], '160.00')
        self.assertEqual((row['from'], row['to']), ('19.10.2026', '25.10.2026'))
        self.assertEqual(row['type'], 'Основной')
        self.assertEqual(row['loyalty_compensation'], '2 571.93')
        self.assertEqual(row['reward_adjustment'], '0.00')
        self.assertEqual(row['loyalty_fee'], '47.71')
        self.assertEqual(row['loyalty_points'], '350.00')
        self.assertEqual(row['payment_schedule'], '0.00')
        self.assertEqual(row['total_to_pay'], '514 684.50')
        self.assertContains(page, '160.00 RUB')
        self.assertContains(page, '514 684.50 RUB')
        self.assertContains(page, '19.10.2026 — 25.10.2026')
        self.assertContains(page, 'class="deduction-trigger"')
        self.assertContains(page, 'id="deduction-panel-835092276" hidden')
        self.assertNotContains(page, '⌄')
        self.assertNotContains(page, 'Все поля')

    @patch('dashboard.views.start_detail_worker')
    def test_buyout_report_type_is_named(self, _worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 2, 'reportType': 2}],
        )
        self.assertEqual(self.client.get(f'/?snapshot={snapshot.pk}').context['report_rows'][0]['type'], 'По выкупам')

    @patch('dashboard.services.detail_worker.close_old_connections')
    @patch('dashboard.services.detail_worker.time.sleep')
    @patch('dashboard.services.detail_worker.fetch_deduction_page')
    def test_automatic_detail_groups_by_reason(self, fetch, _sleep, _close):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
        )
        fetch.side_effect = [[
            {'reportId': 835092276, 'rrdId': 41, 'deduction': '100000',
             'bonusTypeName': 'Продвижение'},
            {'reportId': 835092276, 'rrdId': 42, 'deduction': '54330',
             'bonusTypeName': 'Продвижение'},
        ], None]
        _run(snapshot.pk)
        self.assertEqual(fetch.call_args_list[0].args, ('835092276', 0))
        self.assertEqual(fetch.call_args_list[1].args, ('835092276', 42))
        snapshot.refresh_from_db()
        self.assertTrue(snapshot.detail_complete)
        self.assertEqual(ReportDetail.objects.get(report_id='835092276').entries[0]['amount'], '100000')
        with patch('dashboard.views.start_detail_worker'):
            page = self.client.get(f'/?snapshot={snapshot.pk}')
        row = page.context['report_rows'][0]
        self.assertEqual(len(row['detail_rows']), 1)
        self.assertEqual(row['detail_rows'][0]['formatted_amount'], '154 330.00')
        self.assertTrue(row['detail_matches'])
        self.assertNotContains(page, 'Все поля')
        self.assertNotContains(page, 'Продолжить загрузку')

    @patch('dashboard.views.start_detail_worker')
    def test_old_empty_detail_is_repaired_without_reloading_list(self, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
            detail_complete=True,
        )
        ReportDetail.objects.create(report_id='835092276', complete=True, entries=[])
        page = self.client.get(f'/?snapshot={snapshot.pk}')
        snapshot.refresh_from_db()
        detail = ReportDetail.objects.get(report_id='835092276')
        self.assertFalse(snapshot.detail_complete)
        self.assertFalse(detail.complete)
        self.assertEqual(detail.source, 'report')
        self.assertContains(page, 'Детализация ещё загружается')
        worker.assert_called_with(snapshot.pk)

    @patch('dashboard.views.start_detail_worker')
    def test_completed_report_detail_remains_cached(self, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
            detail_complete=True,
        )
        ReportDetail.objects.create(
            report_id='835092276', complete=True, source='report',
            entries=[{'amount': '154330', 'reason': 'Продвижение'}],
        )
        self.client.get(f'/?snapshot={snapshot.pk}')
        self.client.get(f'/?snapshot={snapshot.pk}')
        worker.assert_not_called()

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_detail_request_uses_report_id_and_pagination_cursor(self, post, _token):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = [{'reportId': 835092276, 'rrdId': 42}]
        post.return_value = response
        self.assertEqual(fetch_deduction_page('835092276', 41), response.json.return_value)
        self.assertTrue(post.call_args.args[0].endswith('/detailed/835092276'))
        self.assertEqual(post.call_args.kwargs['json']['rrdId'], 41)

    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_complete_list_is_saved_and_shown(self, post, _token, worker):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = [{
            'reportId': 123,
            'currency': 'RUB',
            'forPaySum': '183.79',
            'deliveryServiceSum': '10.25',
        }]
        post.return_value = response

        page = self.client.post('/', {
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
            'period': 'daily',
        }, follow=True)

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '183.79')
        self.assertEqual(ReportSnapshot.objects.count(), 1)
        self.assertEqual(ReportSnapshot.objects.first().reports[0]['reportId'], 123)
        self.assertEqual(post.call_args.kwargs['json']['period'], 'weekly')
        self.assertEqual(ReportSnapshot.objects.first().period, 'weekly')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'test-token')
        worker.assert_called()
        snapshot = ReportSnapshot.objects.first()
        self.assertRedirects(page, f'/?snapshot={snapshot.pk}')
        self.client.get(f'/?snapshot={snapshot.pk}')
        self.assertEqual(post.call_count, 1)
        self.assertIsNone(self.client.get('/').context['snapshot'])

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_throttle_prevents_immediate_repeat(self, post, _token):
        post.return_value = Mock(status_code=204)
        self.assertEqual(fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily'), [])
        with self.assertRaises(RateLimitError):
            fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily')
        self.assertEqual(post.call_count, 1)

    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_api_error_does_not_replace_saved_data(self, post, _token, _worker):
        ReportSnapshot.objects.create(
            date_from=date(2026, 9, 1), date_to=date(2026, 9, 30),
            period='weekly', reports=[{'reportId': 100}],
        )
        post.return_value = Mock(status_code=403, ok=False)
        page = self.client.post('/', {
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
            'period': 'weekly',
        }, follow=True)
        self.assertContains(page, 'Доступ запрещён')
        self.assertEqual(ReportSnapshot.objects.count(), 1)
        self.assertIsNone(page.context['snapshot'])
        self.assertEqual(page.context['report_rows'], [])

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_full_page_is_not_treated_as_complete(self, post, _token):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = [{'reportId': i} for i in range(1000)]
        post.return_value = response
        with self.assertRaises(WildberriesError):
            fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily')
        self.assertFalse(ReportSnapshot.objects.exists())


class ReportPeriodFormTests(TestCase):
    @patch('dashboard.forms.timezone.localdate', return_value=date(2026, 11, 9))
    def test_weeks_and_month_boundaries_are_allowed(self, _today):
        for start, end in [
            ('2026-10-19', '2026-10-25'),
            ('2026-10-26', '2026-10-31'),
            ('2026-11-01', '2026-11-01'),
            ('2026-10-26', '2026-11-01'),
            ('2026-10-01', '2026-10-31'),
            ('2026-11-02', '2026-11-08'),
        ]:
            with self.subTest(start=start, end=end):
                form = ReportPeriodForm({'date_from': start, 'date_to': end})
                self.assertTrue(form.is_valid(), form.errors)

    @patch('dashboard.forms.timezone.localdate', return_value=date(2026, 11, 9))
    def test_partial_weeks_and_unavailable_dates_are_rejected(self, _today):
        for start, end in [
            ('2026-10-27', '2026-10-31'),
            ('2026-11-01', '2026-11-03'),
            ('2026-11-09', '2026-11-15'),
            ('2026-11-02', '2026-11-01'),
            ('2023-01-01', '2023-01-31'),
            ('2024-01-29', '2026-11-08'),
        ]:
            with self.subTest(start=start, end=end):
                self.assertFalse(ReportPeriodForm({'date_from': start, 'date_to': end}).is_valid())

    @patch('dashboard.forms.timezone.localdate', return_value=date(2024, 3, 4))
    def test_leap_year_month_boundary(self, _today):
        form = ReportPeriodForm({'date_from': '2024-02-26', 'date_to': '2024-02-29'})
        self.assertTrue(form.is_valid(), form.errors)

    @patch('dashboard.views.fetch_report_list')
    def test_invalid_week_does_not_call_wildberries(self, fetch):
        response = self.client.post('/', {'date_from': '2026-10-27', 'date_to': '2026-10-31'})
        self.assertContains(response, 'Период должен начинаться в понедельник')
        fetch.assert_not_called()
