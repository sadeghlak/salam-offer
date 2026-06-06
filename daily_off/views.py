import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import DailyProductSnapshot, DailyRun, Product
from .services import create_or_update_run, mark_product_fetch_error, store_product_snapshot


def snapshot_to_workflow_payload(item):
    return {
        'snapshot_id': item.id,
        'run_key': str(item.run.run_key),
        'business_date': item.business_date.isoformat(),
        'product_id': item.source_product_id,
        'product_title_full': item.title,
        'product_price': item.price,
        'product_primary_price': item.primary_price,
        'product_description': item.description,
        'product_summary': item.summary,
        'product_photo': item.photo_url,
        'product_status': item.product_status,
        'product_inventory': item.inventory,
        'product_is_available': item.is_available,
        'product_is_saleable': item.is_saleable,
        'product_is_showable': item.is_showable,
        'product_is_wholesale': item.is_wholesale,
        'product_review_count': item.review_count,
        'product_rating': item.rating,
        'product_preparation_day': item.preparation_day,
        'product_net_weight': item.net_weight,
        'product_packaged_weight': item.packaged_weight,
        'product_unit_quantity': item.unit_quantity,
        'product_unit_type': item.unit_type,
        'product_weight_text': item.weight_text,
        'product_category_title': item.category_title,
        'product_category_parent_title': item.category_parent_title,
        'product_navigation_title': item.navigation_title,
        'product_navigation_slug': item.navigation_slug,
        'vendor_name': item.vendor_name,
        'vendor_identifier': item.vendor_identifier,
        'vendor_city': item.vendor_city,
        'vendor_province': item.vendor_province,
        'vendor_summary': item.vendor_summary,
        'vendor_status': item.vendor_status,
        'product_attributes_text': item.attributes_text,
        'product_category_list_text': item.category_list_text,
        'product_raw_json': item.raw_json,
        'details_status': item.details_status,
        'status_row': item.status_row,
    }


def parse_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return None


def parse_business_date(value):
    if not value:
        return date.today()
    parsed = parse_date(str(value))
    return parsed or date.today()


@csrf_exempt
@require_POST
def api_create_run(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    run = create_or_update_run(
        business_date=parse_business_date(payload.get('business_date')),
        run_key=payload.get('run_key') or None,
        input_count=int(payload.get('input_count') or 0),
        status=payload.get('status') or DailyRun.Status.RUNNING,
        config_json=payload.get('config_json') or {},
        notes=payload.get('notes') or '',
    )
    return JsonResponse({'ok': True, 'run_key': str(run.run_key), 'run_id': run.id, 'status': run.status})


@csrf_exempt
@require_POST
def api_ingest_product(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    run_key = payload.get('run_key')
    raw_product = payload.get('product') or payload.get('raw_product') or payload
    if not run_key:
        return JsonResponse({'ok': False, 'error': 'run_key_required'}, status=400)

    run = get_object_or_404(DailyRun, run_key=run_key)

    try:
        snapshot = store_product_snapshot(run=run, raw_product=raw_product, business_date=run.business_date)
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    return JsonResponse({
        'ok': True,
        'snapshot_id': snapshot.id,
        'product_id': snapshot.source_product_id,
        'analysis_status': snapshot.analysis_status,
    })


@csrf_exempt
@require_POST
def api_product_error(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    run = get_object_or_404(DailyRun, run_key=payload.get('run_key'))
    snapshot = mark_product_fetch_error(
        run=run,
        product_id=int(payload.get('product_id') or 0),
        error_message=payload.get('error_message') or 'unknown error',
        business_date=run.business_date,
    )
    return JsonResponse({'ok': True, 'snapshot_id': snapshot.id, 'product_id': snapshot.source_product_id})


@require_GET
def api_pending_analysis(request):
    limit = int(request.GET.get('limit') or 20)
    items = DailyProductSnapshot.objects.filter(
        analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING,
        fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED,
    ).select_related('product', 'run').order_by('business_date', 'id')[:limit]

    return JsonResponse({
        'ok': True,
        'items': [snapshot_to_workflow_payload(item) for item in items],
    })


def dashboard_home(request):
    runs = DailyRun.objects.all()[:20]
    totals = {
        'runs': DailyRun.objects.count(),
        'products': Product.objects.count(),
        'snapshots': DailyProductSnapshot.objects.count(),
        'pending_analysis': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING).count(),
    }
    return render(request, 'daily_off/dashboard.html', {'runs': runs, 'totals': totals})


def run_detail(request, run_key):
    run = get_object_or_404(DailyRun, run_key=run_key)
    base_snapshots = run.snapshots.select_related('product').order_by('id')

    category = request.GET.get('category') or ''
    analysis_status = request.GET.get('analysis_status') or ''

    category_options = list(
        base_snapshots.exclude(category_title='')
        .order_by('category_title')
        .values_list('category_title', flat=True)
        .distinct()
    )
    status_options = list(
        base_snapshots.exclude(analysis_status='')
        .order_by('analysis_status')
        .values_list('analysis_status', flat=True)
        .distinct()
    )

    snapshots = base_snapshots
    if category:
        snapshots = snapshots.filter(category_title=category)
    if analysis_status:
        snapshots = snapshots.filter(analysis_status=analysis_status)

    return render(request, 'daily_off/run_detail.html', {
        'run': run,
        'snapshots': snapshots,
        'category_options': category_options,
        'status_options': status_options,
        'selected_category': category,
        'selected_analysis_status': analysis_status,
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product, basalam_product_id=product_id)
    snapshots = product.daily_snapshots.select_related('run').order_by('-business_date', '-captured_at')
    latest_snapshot = snapshots.first()
    return render(request, 'daily_off/product_detail.html', {
        'product': product,
        'snapshots': snapshots,
        'latest_snapshot': latest_snapshot,
    })
