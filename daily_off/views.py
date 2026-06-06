import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import DailyProductSnapshot, DailyRun, Product
from .services import create_or_update_run, mark_product_fetch_error, store_product_snapshot


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
        'items': [
            {
                'snapshot_id': item.id,
                'run_key': str(item.run.run_key),
                'business_date': item.business_date.isoformat(),
                'product_id': item.source_product_id,
                'title': item.title,
                'price': item.price,
                'photo_url': item.photo_url,
                'raw_json': item.raw_json,
            }
            for item in items
        ],
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
    snapshots = run.snapshots.select_related('product').order_by('id')
    return render(request, 'daily_off/run_detail.html', {'run': run, 'snapshots': snapshots})


def product_detail(request, product_id):
    product = get_object_or_404(Product, basalam_product_id=product_id)
    snapshots = product.daily_snapshots.select_related('run').order_by('-business_date', '-captured_at')
    return render(request, 'daily_off/product_detail.html', {'product': product, 'snapshots': snapshots})
