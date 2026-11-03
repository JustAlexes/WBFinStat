from django.db import models


class ReportSnapshot(models.Model):
    """One complete response for a requested WB report period."""

    date_from = models.DateField()
    date_to = models.DateField()
    period = models.CharField(max_length=6)
    reports = models.JSONField(default=list)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fetched_at', '-id']


class FetchThrottle(models.Model):
    """The next allowed time for a request to the reports list endpoint."""

    key = models.CharField(max_length=40, primary_key=True)
    next_allowed_at = models.DateTimeField()


class ReportDetail(models.Model):
    report_id = models.CharField(max_length=32, primary_key=True)
    cursor = models.BigIntegerField(default=0)
    entries = models.JSONField(default=list)
    complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
