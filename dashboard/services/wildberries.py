"""Minimal client for the official Wildberries financial reports list."""

import os
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from dotenv import load_dotenv

from dashboard.models import FetchThrottle

REPORTS_URL = 'https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list'
DETAIL_URL = 'https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed'
COOLDOWN = timedelta(seconds=65)


class WildberriesError(Exception):
    pass


class RateLimitError(WildberriesError):
    pass


def get_token():
    load_dotenv(settings.BASE_DIR / '.env', override=False)
    return os.environ.get('КОСТРИК', '').strip()


def reserve_request(key='sales-reports-list'):
    """Reserve an API call before sending it, including failed attempts."""
    now = timezone.now()
    next_allowed = now + COOLDOWN
    with transaction.atomic():
        FetchThrottle.objects.get_or_create(
            key=key,
            defaults={'next_allowed_at': now},
        )
        updated = FetchThrottle.objects.filter(
            key=key, next_allowed_at__lte=now
        ).update(next_allowed_at=next_allowed)
    if not updated:
        raise RateLimitError(
            'Wildberries разрешает один запрос в минуту. Подождите около минуты '
            'перед повторной загрузкой.'
        )


def fetch_report_list(date_from, date_to, period):
    token = get_token()
    if not token:
        raise WildberriesError('Добавьте токен в файл .env: КОСТРИК=ваш_токен')

    reserve_request()
    payload = {
        'dateFrom': date_from.isoformat(),
        'dateTo': date_to.isoformat(),
        'period': period,
        'limit': 1000,
        'offset': 0,
    }
    try:
        response = requests.post(
            REPORTS_URL,
            headers={'Authorization': token},
            json=payload,
            timeout=(5, 30),
        )
    except requests.RequestException as exc:
        raise WildberriesError(
            'Не удалось связаться с Wildberries. Проверьте подключение и повторите позже.'
        ) from exc

    if response.status_code == 204:
        return []
    if response.status_code == 401:
        raise WildberriesError('Токен отклонён Wildberries (401). Проверьте значение КОСТРИК.')
    if response.status_code == 403:
        raise WildberriesError(
            'Доступ запрещён (403). Нужен персональный или сервисный токен '
            'с категорией «Финансы».'
        )
    if response.status_code == 429:
        retry = response.headers.get('X-Ratelimit-Retry')
        suffix = f' Повторите через {retry} сек.' if retry and retry.isdigit() else ''
        raise RateLimitError('Превышен лимит запросов Wildberries.' + suffix)
    if not response.ok:
        raise WildberriesError(f'Wildberries вернул ошибку HTTP {response.status_code}.')

    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesError('Wildberries вернул ответ не в формате JSON.') from exc
    if not isinstance(data, list) or any(
        not isinstance(item, dict) or 'reportId' not in item for item in data
    ):
        raise WildberriesError('Формат ответа Wildberries отличается от ожидаемого.')
    if len(data) >= 1000:
        raise WildberriesError(
            'В ответе достигнут предел 1000 отчётов. Выберите более короткий период, '
            'чтобы не показать неполные данные.'
        )
    return data


def fetch_deduction_page(date_from, date_to, period, cursor):
    """Return one detail page; None means WB confirmed the end (204)."""
    token = get_token()
    if not token:
        raise WildberriesError('Добавьте токен в файл .env: КОСТРИК=ваш_токен')
    reserve_request('sales-reports-detail')
    try:
        response = requests.post(
            DETAIL_URL,
            headers={'Authorization': token},
            json={
                'limit': 100000,
                'rrdId': cursor,
                'dateFrom': date_from.isoformat(),
                'dateTo': date_to.isoformat(),
                'period': period,
                'fields': [
                    'reportId', 'rrdId', 'deduction', 'bonusTypeName',
                    'sellerOperName', 'rrDate',
                ],
            },
            timeout=(5, 60),
        )
    except requests.RequestException as exc:
        raise WildberriesError('Не удалось загрузить детализацию Wildberries.') from exc
    if response.status_code == 204:
        return None
    if response.status_code in (401, 403):
        raise WildberriesError('Доступ к детализации запрещён. Проверьте токен категории «Финансы».')
    if response.status_code == 429:
        raise RateLimitError('Лимит Wildberries: повторите загрузку детализации позже.')
    if not response.ok:
        raise WildberriesError(f'Wildberries вернул ошибку HTTP {response.status_code}.')
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesError('Детализация пришла не в формате JSON.') from exc
    if not isinstance(data, list) or not data or any(
        not isinstance(row, dict) or 'rrdId' not in row or 'reportId' not in row
        for row in data
    ):
        raise WildberriesError('Формат детализации отличается от ожидаемого.')
    if int(data[-1]['rrdId']) <= int(cursor):
        raise WildberriesError('Wildberries не продвинул курсор детализации.')
    return data
