from django.urls import path

from . import views

app_name = 'daily_off'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard'),
    path('management/users/', views.management_users_dashboard, name='management_users'),
    path('runs/<uuid:run_key>/', views.run_detail, name='run_detail'),
    path('runs/<uuid:run_key>/delete/', views.delete_run, name='delete_run'),
    path('runs/<uuid:run_key>/analysis-candidates/export.csv', views.export_run_analysis_candidates_csv, name='export_run_analysis_candidates_csv'),
    path('products/<int:product_id>/', views.product_detail, name='product_detail'),
    path('api/runs/', views.api_create_run, name='api_create_run'),
    path('api/runs/products/next-batch/', views.api_next_product_batch, name='api_next_product_batch'),
    path('api/products/ingest/', views.api_ingest_product, name='api_ingest_product'),
    path('api/products/error/', views.api_product_error, name='api_product_error'),
    path('api/analysis/pending/', views.api_pending_analysis, name='api_pending_analysis'),
    path('api/analysis/claim/', views.api_claim_analysis, name='api_claim_analysis'),
    path('api/analysis/requeue-stale/', views.api_requeue_stale_analysis, name='api_requeue_stale_analysis'),
    path('api/analysis/result/', views.api_analysis_result, name='api_analysis_result'),
    path('api/analysis/error/', views.api_analysis_error, name='api_analysis_error'),
    path('api/analysis/process-next/', views.api_process_next_analysis, name='api_process_next_analysis'),
    path('api/analysis/process-batch/', views.api_process_analysis_batch, name='api_process_analysis_batch'),
    path('api/analysis/snapshots/<int:snapshot_id>/run/', views.api_run_snapshot_analysis, name='api_run_snapshot_analysis'),
    path('api/analysis/snapshots/<int:snapshot_id>/status/', views.api_snapshot_analysis_status, name='api_snapshot_analysis_status'),
    path('api/analysis/snapshots/<int:snapshot_id>/logs/', views.api_snapshot_analysis_logs, name='api_snapshot_analysis_logs'),
    path('api/runs/<uuid:run_key>/analysis-rerun/', views.api_rerun_analysis, name='api_rerun_analysis'),
    path('api/runs/<uuid:run_key>/analysis-status/', views.api_run_analysis_status, name='api_run_analysis_status'),
    path('api/runs/finish/', views.api_finish_run, name='api_finish_run'),
]
