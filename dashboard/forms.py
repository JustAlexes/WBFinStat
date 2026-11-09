from calendar import monthrange
from datetime import date, timedelta

from django import forms
from django.utils import timezone


class ReportPeriodForm(forms.Form):
    date_from = forms.DateField(
        label='Начало периода',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'hidden'}),
    )
    date_to = forms.DateField(
        label='Конец периода',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'hidden'}),
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('date_from')
        end = cleaned.get('date_to')
        if start and end:
            if start > end:
                raise forms.ValidationError('Дата начала должна быть раньше даты конца.')
            if start < date(2024, 1, 29):
                raise forms.ValidationError('Отчёты доступны с 29 января 2024 года.')
            if end > timezone.localdate():
                raise forms.ValidationError('Дата конца не может быть в будущем.')
            if end - start > timedelta(days=365):
                raise forms.ValidationError('Выберите период не длиннее 365 дней.')
            if start.weekday() != 0 and start.day != 1:
                raise forms.ValidationError(
                    'Период должен начинаться в понедельник или в первый день месяца.'
                )
            if end.weekday() != 6 and end.day != monthrange(end.year, end.month)[1]:
                raise forms.ValidationError(
                    'Период должен заканчиваться в воскресенье или в последний день месяца.'
                )
        return cleaned
