import uuid

from django.db import models
from django.utils import timezone


class DailyRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        PARTIAL_FAILED = 'partial_failed', 'Partial failed'
        FAILED = 'failed', 'Failed'

    run_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_date = models.DateField(db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    source_type = models.CharField(max_length=64, default='daily_off_query')
    input_count = models.PositiveIntegerField(default=0)
    fetched_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-business_date', '-created_at']

    def __str__(self):
        return f'{self.business_date} / {self.status}'


class Product(models.Model):
    basalam_product_id = models.BigIntegerField(unique=True, db_index=True)
    latest_title = models.CharField(max_length=255, blank=True)
    latest_price = models.BigIntegerField(default=0)
    latest_primary_price = models.BigIntegerField(default=0)
    latest_photo_url = models.URLField(max_length=700, blank=True)
    latest_vendor_identifier = models.CharField(max_length=160, blank=True)
    latest_product_url = models.URLField(max_length=700, blank=True)
    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.basalam_product_id} - {self.latest_title}'


class DailyProductSnapshot(models.Model):
    class FetchStatus(models.TextChoices):
        DETAILS_FETCHED = 'details_fetched', 'Details fetched'
        FETCH_ERROR = 'fetch_error', 'Fetch error'

    class AnalysisStatus(models.TextChoices):
        PENDING = 'analysis_pending', 'Analysis pending'
        RUNNING = 'analysis_running', 'Analysis running'
        ANALYZED = 'analyzed', 'Analyzed'
        NO_MATCH = 'no_match', 'No match'
        ERROR = 'analysis_error', 'Analysis error'

    run = models.ForeignKey(DailyRun, on_delete=models.CASCADE, related_name='snapshots')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='daily_snapshots')
    source_product_id = models.BigIntegerField(db_index=True)
    business_date = models.DateField(db_index=True)
    captured_at = models.DateTimeField(default=timezone.now, db_index=True)

    title = models.CharField(max_length=255, blank=True)
    price = models.BigIntegerField(default=0)
    primary_price = models.BigIntegerField(default=0)
    description = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    photo_url = models.URLField(max_length=700, blank=True)
    product_status = models.CharField(max_length=128, blank=True)
    inventory = models.IntegerField(default=0)
    is_available = models.BooleanField(default=False)
    is_saleable = models.BooleanField(default=False)
    is_showable = models.BooleanField(default=False)
    is_wholesale = models.BooleanField(default=False)
    review_count = models.PositiveIntegerField(default=0)
    rating = models.FloatField(default=0)
    preparation_day = models.PositiveIntegerField(default=0)
    net_weight = models.FloatField(default=0)
    packaged_weight = models.FloatField(default=0)
    unit_quantity = models.FloatField(default=0)
    unit_type = models.CharField(max_length=128, blank=True)
    weight_text = models.CharField(max_length=255, blank=True)
    category_title = models.CharField(max_length=255, blank=True)
    category_parent_title = models.CharField(max_length=255, blank=True)
    navigation_title = models.CharField(max_length=255, blank=True)
    navigation_slug = models.CharField(max_length=255, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    vendor_identifier = models.CharField(max_length=160, blank=True)
    vendor_city = models.CharField(max_length=255, blank=True)
    vendor_province = models.CharField(max_length=255, blank=True)
    vendor_summary = models.TextField(blank=True)
    vendor_status = models.CharField(max_length=128, blank=True)
    attributes_text = models.TextField(blank=True)
    category_list_text = models.TextField(blank=True)
    raw_json = models.JSONField(default=dict, blank=True)
    details_status = models.CharField(max_length=64, default='DETAILS_FETCHED', db_index=True)
    status_row = models.CharField(max_length=64, default='analysis_pending', db_index=True)

    fetch_status = models.CharField(max_length=32, choices=FetchStatus.choices, default=FetchStatus.DETAILS_FETCHED, db_index=True)
    analysis_status = models.CharField(max_length=32, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING, db_index=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-business_date', '-captured_at']
        constraints = [
            models.UniqueConstraint(fields=['run', 'source_product_id'], name='uniq_daily_snapshot_per_run_product'),
        ]
        indexes = [
            models.Index(fields=['product', '-business_date']),
            models.Index(fields=['business_date', 'analysis_status']),
        ]

    def __str__(self):
        return f'{self.source_product_id} / {self.business_date}'
