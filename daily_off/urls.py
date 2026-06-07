from django.urls import path

from . import views

app_name = 'daily_off'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard'),
    path('runs/<uuid:run_key>/', views.run_detail, name='run_detail'),
    path('products/<int:product_id>/', views.product_detail, name='product_detail'),
    path('api/runs/', views.api_create_run, name='api_create_run'),
    path('api/products/ingest/', views.api_ingest_product, name='api_ingest_product'),
    path('api/products/error/', views.api_product_error, name='api_product_error'),
    path('api/analysis/pending/', views.api_pending_analysis, name='api_pending_analysis'),
    path('api/analysis/claim/', views.api_claim_analysis, name='api_claim_analysis'),
    path('api/analysis/result/', views.api_analysis_result, name='api_analysis_result'),
    path('api/analysis/error/', views.api_analysis_error, name='api_analysis_error'),
    path('api/runs/finish/', views.api_finish_run, name='api_finish_run'),
]
