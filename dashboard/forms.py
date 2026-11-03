from datetime import date, timedelta

from django import forms
from django.utils import timezone


class ReportPeriodForm(forms.Form):
    date_from = forms.DateField(
        label='Начало', widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_to = forms.DateField(
        label='Конец', widget=forms.DateInput(attrs={'type': 'date'})
    )
    period = forms.ChoiceField(
        label='Тип отчёта',
        choices=[('weekly', 'Еженедельный'), ('daily', 'Ежедневный')],
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
        return cleaned
