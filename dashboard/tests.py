from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase

from dashboard.models import ReportSnapshot
from dashboard.services.wildberries import (
    RateLimitError,
    WildberriesError,
    fetch_report_list,
)


class WildberriesReportTests(TestCase):
    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_complete_list_is_saved_and_shown(self, post, _token):
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
            'period': 'weekly',
        })

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '183.79')
        self.assertEqual(ReportSnapshot.objects.count(), 1)
        self.assertEqual(ReportSnapshot.objects.first().reports[0]['reportId'], 123)
        self.assertEqual(post.call_args.kwargs['json']['period'], 'weekly')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'test-token')

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_throttle_prevents_immediate_repeat(self, post, _token):
        post.return_value = Mock(status_code=204)
        self.assertEqual(fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily'), [])
        with self.assertRaises(RateLimitError):
            fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily')
        self.assertEqual(post.call_count, 1)

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_api_error_does_not_replace_saved_data(self, post, _token):
        ReportSnapshot.objects.create(
            date_from=date(2026, 9, 1), date_to=date(2026, 9, 30),
            period='weekly', reports=[{'reportId': 100}],
        )
        post.return_value = Mock(status_code=403, ok=False)
        page = self.client.post('/', {
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
            'period': 'weekly',
        })
        self.assertContains(page, 'Доступ запрещён')
        self.assertEqual(ReportSnapshot.objects.count(), 1)

    @patch('dashboard.services.wildberries.get_token', return_value='test-token')
    @patch('dashboard.services.wildberries.requests.post')
    def test_full_page_is_not_treated_as_complete(self, post, _token):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = [{'reportId': i} for i in range(1000)]
        post.return_value = response
        with self.assertRaises(WildberriesError):
            fetch_report_list(date(2026, 10, 1), date(2026, 10, 2), 'daily')
        self.assertFalse(ReportSnapshot.objects.exists())
