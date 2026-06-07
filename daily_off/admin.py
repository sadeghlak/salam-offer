from django.contrib import admin

from .models import DailyProductSnapshot, DailyRun, Product


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
