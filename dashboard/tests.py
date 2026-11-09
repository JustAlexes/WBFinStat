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
    def open_result(self, snapshot):
        session = self.client.session
        session['report_result_id'] = snapshot.pk
        session.save()
        return self.client.get('/')

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
    def test_old_result_url_cannot_restore_reports(self, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '154330'}],
            detail_error='Не удалось загрузить детализацию Wildberries.',
        )
        page = self.client.get(f'/?snapshot={snapshot.pk}')
        self.assertIsNone(page.context['snapshot'])
        self.assertNotContains(page, '835092276')
        self.assertNotContains(page, 'Не удалось загрузить детализацию')
        worker.assert_not_called()

    @patch('dashboard.views.start_detail_worker')
    def test_result_is_displayed_once_and_status_updates_without_restoring_home(self, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
            period='weekly', reports=[{'reportId': 835092276, 'deductionSum': '0'}],
        )
        page = self.open_result(snapshot)
        self.assertContains(page, '835092276')
        status = self.client.get(f'/reports/status/{snapshot.pk}/').json()
        self.assertTrue(status['complete'])
        self.assertIn('835092276', status['html'])
        self.assertIsNone(self.client.get('/').context['snapshot'])
        self.assertIsNone(self.client.get(f'/?snapshot={snapshot.pk}').context['snapshot'])
        worker.assert_not_called()

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
        page = self.open_result(snapshot)
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
        self.assertEqual(self.open_result(snapshot).context['report_rows'][0]['type'], 'По выкупам')

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
            page = self.open_result(snapshot)
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
        page = self.open_result(snapshot)
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
        self.open_result(snapshot)
        self.open_result(snapshot)
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
        self.assertEqual(page.redirect_chain, [('/', 302)])
        self.assertIsNone(self.client.get('/').context['snapshot'])
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

    @patch('dashboard.views.get_token', return_value='')
    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.views.fetch_report_list')
    def test_same_period_reuses_saved_reports_and_details_without_token(self, fetch, worker, _token):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 19), date_to=date(2026, 10, 25), period='weekly',
            reports=[{'reportId': 835092276, 'deductionSum': '154330'}], detail_complete=True,
        )
        ReportDetail.objects.create(
            report_id='835092276', source='report', complete=True,
            entries=[{'reason': 'Продвижение', 'amount': '154330'}],
        )
        for _ in range(2):
            page = self.client.post('/', {
                'date_from': '2026-10-19', 'date_to': '2026-10-25',
            }, follow=True)
            self.assertEqual(page.context['snapshot'].pk, snapshot.pk)
            self.assertContains(page, 'Показаны сохранённые отчёты: 1.')
            self.assertContains(page, '154 330.00')
        self.assertEqual(ReportSnapshot.objects.count(), 1)
        fetch.assert_not_called()
        worker.assert_not_called()
        self.assertIsNone(self.client.get('/').context['snapshot'])

    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.views.fetch_report_list')
    def test_cached_list_resumes_failed_detail_from_saved_cursor(self, fetch, worker):
        snapshot = ReportSnapshot.objects.create(
            date_from=date(2026, 10, 19), date_to=date(2026, 10, 25), period='weekly',
            reports=[{'reportId': 835092276, 'deductionSum': '154330'}], detail_error='Сбой сети',
        )
        ReportDetail.objects.create(
            report_id='835092276', source='report', cursor=42,
            entries=[{'reason': 'Продвижение', 'amount': '100000'}],
        )
        self.client.post('/', {'date_from': '2026-10-19', 'date_to': '2026-10-25'}, follow=True)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.detail_error, '')
        detail = ReportDetail.objects.get(report_id='835092276')
        self.assertEqual(detail.cursor, 42)
        self.assertEqual(len(detail.entries), 1)
        fetch.assert_not_called()
        worker.assert_called_with(snapshot.pk)

    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.views.fetch_report_list', return_value=[{'reportId': 200, 'deductionSum': '0'}])
    def test_explicit_refresh_bypasses_saved_period(self, fetch, _worker):
        ReportSnapshot.objects.create(
            date_from=date(2026, 10, 19), date_to=date(2026, 10, 25), period='weekly',
            reports=[{'reportId': 100, 'deductionSum': '0'}],
        )
        page = self.client.post('/', {
            'date_from': '2026-10-19', 'date_to': '2026-10-25', 'refresh': '1',
        }, follow=True)
        self.assertEqual(page.context['snapshot'].reports[0]['reportId'], 200)
        self.assertEqual(ReportSnapshot.objects.count(), 2)
        fetch.assert_called_once_with(date(2026, 10, 19), date(2026, 10, 25), 'weekly')

    @patch('dashboard.views.start_detail_worker')
    @patch('dashboard.views.fetch_report_list', return_value=[{'reportId': 200, 'deductionSum': '0'}])
    def test_empty_saved_response_does_not_hide_later_reports(self, fetch, _worker):
        ReportSnapshot.objects.create(
            date_from=date(2026, 10, 19), date_to=date(2026, 10, 25), period='weekly', reports=[],
        )
        page = self.client.post('/', {
            'date_from': '2026-10-19', 'date_to': '2026-10-25',
        }, follow=True)
        self.assertEqual(page.context['snapshot'].reports[0]['reportId'], 200)
        fetch.assert_called_once()

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
