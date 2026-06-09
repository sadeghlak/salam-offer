from django.contrib import admin

from .models import AnalysisCandidate, AnalysisStatusLog, DailyProductSnapshot, DailyRun, Product


@admin.register(DailyRun)
class DailyRunAdmin(admin.ModelAdmin):
    list_display = ('business_date', 'run_key', 'status', 'input_count', 'fetched_count', 'error_count', 'created_at')
    list_filter = ('status', 'business_date', 'source_type')
    search_fields = ('run_key', 'notes')
    readonly_fields = ('run_key', 'created_at', 'updated_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('basalam_product_id', 'latest_title', 'latest_price', 'latest_vendor_identifier', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('basalam_product_id', 'latest_title', 'latest_vendor_identifier')
    readonly_fields = ('first_seen_at', 'updated_at')


@admin.register(DailyProductSnapshot)
class DailyProductSnapshotAdmin(admin.ModelAdmin):
    list_display = ('source_product_id', 'business_date', 'title', 'price', 'fetch_status', 'analysis_status', 'vendor_name')
    list_filter = ('business_date', 'fetch_status', 'analysis_status')
    search_fields = ('source_product_id', 'title', 'vendor_name', 'vendor_identifier')
    readonly_fields = ('captured_at', 'created_at', 'updated_at')


@admin.register(AnalysisCandidate)
class AnalysisCandidateAdmin(admin.ModelAdmin):
    list_display = ('id', 'snapshot', 'candidate_id', 'decision', 'candidate_price', 'similarity_score', 'unit_equivalent', 'created_at')
    list_filter = ('decision', 'unit_comparable', 'unit_equivalent', 'title_measurement_used', 'created_at')
    search_fields = ('snapshot__source_product_id', 'snapshot__title', 'candidate_id', 'candidate_title', 'rejection_reason_text')
    readonly_fields = ('snapshot', 'run', 'product', 'request_id', 'created_at')


@admin.register(AnalysisStatusLog)
class AnalysisStatusLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'event_type', 'snapshot', 'from_status', 'to_status', 'actor', 'request_id')
    list_filter = ('event_type', 'from_status', 'to_status', 'actor', 'created_at')
    search_fields = ('snapshot__source_product_id', 'snapshot__title', 'message', 'request_id')
    readonly_fields = ('snapshot', 'run', 'product', 'from_status', 'to_status', 'status_row', 'event_type', 'message', 'metadata', 'request_id', 'actor', 'created_at')
