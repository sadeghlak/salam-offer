import csv
import json
import logging
from datetime import date
from html import escape

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import AnalysisCandidate, AnalysisStatusLog, DailyProductSnapshot, DailyRun, Product
from .services import (
    analysis_counts_for_run,
    analysis_payload_for_run,
    claim_pending_analysis,
    create_or_update_run,
    enqueue_snapshot_analysis,
    make_request_id,
    mark_analysis_error,
    mark_product_fetch_error,
    next_missing_product_batch,
    process_analysis_batch,
    refresh_run_status,
    requeue_stale_analysis,
    store_analysis_result,
    store_product_snapshot,
)


logger = logging.getLogger(__name__)


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
        from django.utils import timezone
        return timezone.localdate()
    parsed = parse_date(str(value))
    return parsed or date.today()


def parse_int(value, default=0):
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp_limit(value, default=100, maximum=100):
    return max(1, min(parse_int(value, default), maximum))


def counts_for_queryset(queryset):
    counts = {
        'analysis_pending': 0,
        'analysis_running': 0,
        'analyzed': 0,
        'no_match': 0,
        'analysis_error': 0,
    }
    for row in queryset.values('analysis_status').annotate(total=Count('id')):
        counts[row['analysis_status']] = row['total']
    return counts


def compact_analysis_summary(counts):
    return {
        'pending': counts.get(DailyProductSnapshot.AnalysisStatus.PENDING, counts.get('analysis_pending', 0)),
        'running': counts.get(DailyProductSnapshot.AnalysisStatus.RUNNING, counts.get('analysis_running', 0)),
        'analyzed': counts.get(DailyProductSnapshot.AnalysisStatus.ANALYZED, counts.get('analyzed', 0)),
        'no_match': counts.get(DailyProductSnapshot.AnalysisStatus.NO_MATCH, counts.get('no_match', 0)),
        'error': counts.get(DailyProductSnapshot.AnalysisStatus.ERROR, counts.get('analysis_error', 0)),
    }


def run_api_payload(run):
    return {
        'ok': True,
        'run_key': str(run.run_key),
        'run_id': run.id,
        'business_date': run.business_date.isoformat(),
        'status': run.status,
        'input_count': run.input_count,
        'fetched_count': run.fetched_count,
        'error_count': run.error_count,
        'analysis': compact_analysis_summary(analysis_counts_for_run(run)),
    }


def snapshot_analysis_payload(snapshot, **extra):
    payload = {
        'ok': True,
        'snapshot_id': snapshot.id,
        'product_id': snapshot.source_product_id,
        'analysis_status': snapshot.analysis_status,
        'status_row': snapshot.status_row,
        'accepted_candidates_count': snapshot.accepted_candidates_count,
        'product_url1': snapshot.product_url1,
        'product_url2': snapshot.product_url2,
        'product_url3': snapshot.product_url3,
        'error_message': snapshot.error_message,
        'is_complete': snapshot.analysis_status in {
            DailyProductSnapshot.AnalysisStatus.ANALYZED,
            DailyProductSnapshot.AnalysisStatus.NO_MATCH,
            DailyProductSnapshot.AnalysisStatus.ERROR,
        },
        'run': analysis_payload_for_run(snapshot.run),
    }
    payload.update(extra)
    return payload


def filter_analysis_scope(queryset, *, run_key=None, business_date_value=None):
    if run_key:
        return queryset.filter(run__run_key=run_key)
    business_date_value = parse_business_date(business_date_value)
    return queryset.filter(business_date=business_date_value)


@csrf_exempt
@require_POST
def api_create_run(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    run = create_or_update_run(
        business_date=parse_business_date(payload.get('business_date')),
        run_key=payload.get('run_key') or None,
        input_count=parse_int(payload.get('input_count')),
        status=payload.get('status') or DailyRun.Status.RUNNING,
        config_json=payload.get('config_json') or {},
        notes=payload.get('notes') or '',
    )
    return JsonResponse(run_api_payload(run))


@csrf_exempt
@require_POST
def api_next_product_batch(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    raw_product_ids = payload.get('product_ids') or payload.get('products') or []
    if not isinstance(raw_product_ids, list):
        return JsonResponse({'ok': False, 'error': 'product_ids_must_be_list'}, status=400)

    product_ids = []
    for item in raw_product_ids:
        if isinstance(item, dict):
            product_ids.append(item.get('product_id') or item.get('id'))
        else:
            product_ids.append(item)

    run, batch_ids, existing_count, remaining_count = next_missing_product_batch(
        business_date=parse_business_date(payload.get('business_date')),
        product_ids=product_ids,
        limit=clamp_limit(payload.get('limit')),
        config_json=payload.get('config_json') or {},
        notes=payload.get('notes') or 'daily-off import batch requested from n8n',
    )

    return JsonResponse({
        'ok': True,
        'run_key': str(run.run_key),
        'run_id': run.id,
        'business_date': run.business_date.isoformat(),
        'input_count': run.input_count,
        'existing_count': existing_count,
        'remaining_count': remaining_count,
        'batch_count': len(batch_ids),
        'is_complete': remaining_count == 0,
        'product_ids': batch_ids,
        'products': [{'product_id': product_id} for product_id in batch_ids],
    })


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
        product_id=parse_int(payload.get('product_id')),
        error_message=payload.get('error_message') or 'unknown error',
        business_date=run.business_date,
    )
    return JsonResponse({'ok': True, 'snapshot_id': snapshot.id, 'product_id': snapshot.source_product_id})


@require_GET
def api_pending_analysis(request):
    limit = clamp_limit(request.GET.get('limit'))
    queryset = DailyProductSnapshot.objects.filter(
        analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING,
        fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED,
    )
    queryset = filter_analysis_scope(
        queryset,
        run_key=request.GET.get('run_key') or None,
        business_date_value=request.GET.get('business_date') or None,
    )
    items = queryset.select_related('product', 'run').order_by('id')[:limit]

    return JsonResponse({
        'ok': True,
        'items': [snapshot_to_workflow_payload(item) for item in items],
    })


@csrf_exempt
@require_POST
def api_claim_analysis(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    try:
        items = claim_pending_analysis(
            limit=clamp_limit(payload.get('limit')),
            run_key=payload.get('run_key') or None,
            business_date=parse_business_date(payload.get('business_date')) if payload.get('business_date') else None,
        )
    except (ValidationError, ValueError) as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    return JsonResponse({
        'ok': True,
        'claimed_count': len(items),
        'items': [snapshot_to_workflow_payload(item) for item in items],
    })


@csrf_exempt
@require_POST
def api_requeue_stale_analysis(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    requeued_count = requeue_stale_analysis(
        run_key=payload.get('run_key') or None,
        business_date=parse_business_date(payload.get('business_date')) if payload.get('business_date') else None,
        older_than_minutes=parse_int(payload.get('older_than_minutes'), 120),
    )
    return JsonResponse({
        'ok': True,
        'requeued_count': requeued_count,
    })


@csrf_exempt
@require_POST
def api_analysis_result(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    try:
        snapshot = store_analysis_result(
            snapshot_id=payload.get('snapshot_id'),
            run_key=payload.get('run_key'),
            product_id=payload.get('product_id') or payload.get('source_product_id'),
            result=payload,
        )
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except (ObjectDoesNotExist, ValidationError):
        return JsonResponse({'ok': False, 'error': 'snapshot_not_found'}, status=404)

    return JsonResponse({
        'ok': True,
        'snapshot_id': snapshot.id,
        'product_id': snapshot.source_product_id,
        'analysis_status': snapshot.analysis_status,
        'accepted_candidates_count': snapshot.accepted_candidates_count,
    })


@csrf_exempt
@require_POST
def api_analysis_error(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    try:
        snapshot = mark_analysis_error(
            snapshot_id=payload.get('snapshot_id'),
            run_key=payload.get('run_key'),
            product_id=payload.get('product_id') or payload.get('source_product_id'),
            error_message=payload.get('error_message') or 'unknown analysis error',
            request_id=payload.get('request_id') or '',
            actor=payload.get('actor') or 'django_api',
        )
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except (ObjectDoesNotExist, ValidationError):
        return JsonResponse({'ok': False, 'error': 'snapshot_not_found'}, status=404)

    return JsonResponse({
        'ok': True,
        'snapshot_id': snapshot.id,
        'product_id': snapshot.source_product_id,
        'analysis_status': snapshot.analysis_status,
    })


@csrf_exempt
@require_POST
def api_run_snapshot_analysis(request, snapshot_id):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    request_id = payload.get('request_id') or make_request_id()
    actor = payload.get('actor') or 'django_api'
    force = bool(payload.get('force'))
    stale_minutes = parse_int(payload.get('older_than_minutes'), 30)
    logger.info(
        'analysis snapshot queue requested snapshot_id=%s request_id=%s actor=%s force=%s stale_minutes=%s',
        snapshot_id,
        request_id,
        actor,
        force,
        stale_minutes,
    )

    try:
        snapshot, queued, queue_state = enqueue_snapshot_analysis(
            snapshot_id=snapshot_id,
            force=force,
            stale_minutes=stale_minutes,
            request_id=request_id,
            actor=actor,
        )
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except ObjectDoesNotExist:
        return JsonResponse({'ok': False, 'error': 'snapshot_not_found'}, status=404)

    status_code = 202 if queued else 200
    return JsonResponse(snapshot_analysis_payload(
        snapshot,
        request_id=request_id,
        queued=queued,
        queue_state=queue_state,
    ), status=status_code)


@require_GET
def api_snapshot_analysis_status(request, snapshot_id):
    snapshot = get_object_or_404(DailyProductSnapshot.objects.select_related('run', 'product'), id=snapshot_id)
    return JsonResponse(snapshot_analysis_payload(snapshot))


@csrf_exempt
@require_POST
def api_process_next_analysis(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    result = process_analysis_batch(
        run_key=payload.get('run_key') or None,
        business_date=parse_business_date(payload.get('business_date')) if payload.get('business_date') else None,
        limit=clamp_limit(payload.get('limit'), default=1, maximum=3),
        older_than_minutes=parse_int(payload.get('older_than_minutes'), 30),
        request_id=payload.get('request_id') or make_request_id(),
        actor=payload.get('actor') or 'django_api',
    )
    return JsonResponse(result)


@csrf_exempt
@require_POST
def api_process_analysis_batch(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    result = process_analysis_batch(
        run_key=payload.get('run_key') or None,
        business_date=parse_business_date(payload.get('business_date')) if payload.get('business_date') else None,
        limit=clamp_limit(payload.get('limit'), default=10, maximum=10),
        older_than_minutes=parse_int(payload.get('older_than_minutes'), 30),
        request_id=payload.get('request_id') or make_request_id(),
        actor=payload.get('actor') or 'django_api',
    )
    return JsonResponse(result)


@require_GET
def api_run_analysis_status(request, run_key):
    run = get_object_or_404(DailyRun, run_key=run_key)
    payload = analysis_payload_for_run(run)
    analysis = payload['analysis']
    payload.update({
        'ok': True,
        'status': run.status,
        'is_complete': analysis['pending'] == 0 and analysis['running'] == 0,
    })
    return JsonResponse(payload)


@require_GET
def api_snapshot_analysis_logs(request, snapshot_id):
    snapshot = get_object_or_404(DailyProductSnapshot, id=snapshot_id)
    logs = snapshot.analysis_logs.order_by('-created_at', '-id')[:50]
    return JsonResponse({
        'ok': True,
        'snapshot_id': snapshot.id,
        'logs': [
            {
                'id': log.id,
                'created_at': log.created_at.isoformat(),
                'event_type': log.event_type,
                'from_status': log.from_status,
                'to_status': log.to_status,
                'status_row': log.status_row,
                'message': log.message,
                'metadata': log.metadata,
                'actor': log.actor,
                'request_id': log.request_id,
            }
            for log in logs
        ],
    })


@csrf_exempt
@require_POST
def api_finish_run(request):
    payload = parse_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    run_key = payload.get('run_key')
    if not run_key:
        return JsonResponse({'ok': False, 'error': 'run_key_required'}, status=400)

    run = get_object_or_404(DailyRun, run_key=run_key)
    status = payload.get('status') or None
    allowed_statuses = {choice[0] for choice in DailyRun.Status.choices}
    if status and status not in allowed_statuses:
        return JsonResponse({'ok': False, 'error': 'invalid_status'}, status=400)

    run = refresh_run_status(
        run,
        explicit_status=status,
        notes=payload.get('notes') if 'notes' in payload else None,
        finish=True,
    )
    return JsonResponse({
        'ok': True,
        'run_key': str(run.run_key),
        'status': run.status,
        'input_count': run.input_count,
        'fetched_count': run.fetched_count,
        'error_count': run.error_count,
        'analysis': compact_analysis_summary(analysis_counts_for_run(run)),
    })


def csv_value(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ' | '.join([str(item) for item in value])
    return value


def export_run_analysis_candidates_csv(request, run_key):
    run = get_object_or_404(DailyRun, run_key=run_key)
    response = HttpResponse(content_type='application/vnd.ms-excel; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="salam-offer-dataset-{run.business_date}-{run.run_key}.xls"'
    headers = [
        'اسم محصول اصلی',
        'محصول مشابه ۱',
        'محصول مشابه ۲',
        'محصول مشابه ۳',
        'محصول مشابه پیدا نشد؟',
        'وضعیت محصول مشابه ۱',
        'دلیل وضعیت محصول مشابه ۱',
        'وضعیت محصول مشابه ۲',
        'دلیل وضعیت محصول مشابه ۲',
        'وضعیت محصول مشابه ۳',
        'دلیل وضعیت محصول مشابه ۳',
        'محصول مشابه صحیح دیگری که جا افتاده',
        'توضیحات کلی شما',
    ]
    rows = []

    accepted_by_snapshot = {}
    accepted_candidates = (
        AnalysisCandidate.objects
        .filter(run=run, decision=AnalysisCandidate.Decision.ACCEPTED)
        .only('snapshot_id', 'candidate_title', 'similarity_score', 'candidate_price')
        .order_by('snapshot_id', '-similarity_score', 'candidate_price')
    )
    for candidate in accepted_candidates:
        bucket = accepted_by_snapshot.setdefault(candidate.snapshot_id, [])
        if len(bucket) < 3:
            bucket.append(candidate.candidate_title)

    snapshots = run.snapshots.only(
        'id',
        'title',
        'analysis_status',
        'product_url1',
        'product_url2',
        'product_url3',
    ).order_by('id')
    for snapshot in snapshots:
        similar_names = accepted_by_snapshot.get(snapshot.id, [])
        if not similar_names:
            similar_names = [url for url in [snapshot.product_url1, snapshot.product_url2, snapshot.product_url3] if url]
        similar_names = similar_names[:3] + [''] * (3 - len(similar_names))
        no_match = 'بله' if not any(similar_names) or snapshot.analysis_status == DailyProductSnapshot.AnalysisStatus.NO_MATCH else ''
        rows.append([
            snapshot.title,
            similar_names[0],
            similar_names[1],
            similar_names[2],
            no_match,
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
        ])

    response.write('﻿')
    response.write('<html><head><meta charset="utf-8"></head><body>')
    response.write('<table border="1" dir="rtl" style="font-family:Tahoma; border-collapse:collapse;">')
    response.write('<thead><tr>')
    for header in headers:
        response.write(f'<th>{escape(header)}</th>')
    response.write('</tr></thead><tbody>')
    for row in rows:
        response.write('<tr>')
        for value in row:
            response.write(f'<td>{escape(str(value or ""))}</td>')
        response.write('</tr>')
    response.write('</tbody></table></body></html>')
    return response


def dashboard_home(request):
    runs = list(DailyRun.objects.all()[:20])
    for run in runs:
        run.analysis_summary = compact_analysis_summary(analysis_counts_for_run(run))

    totals = {
        'runs': DailyRun.objects.count(),
        'products': Product.objects.count(),
        'snapshots': DailyProductSnapshot.objects.count(),
        'pending_analysis': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING).count(),
        'running_analysis': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.RUNNING).count(),
        'analyzed': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED).count(),
        'no_match': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.NO_MATCH).count(),
        'analysis_errors': DailyProductSnapshot.objects.filter(analysis_status=DailyProductSnapshot.AnalysisStatus.ERROR).count(),
        'fetch_errors': DailyProductSnapshot.objects.filter(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR).count(),
    }
    return render(request, 'daily_off/dashboard.html', {'runs': runs, 'totals': totals})


def run_detail(request, run_key):
    run = DailyRun.objects.filter(run_key=run_key).first()
    if run is None:
        messages.error(request, 'این اجرا در دیتابیس فعلی سایت پیدا نشد. اگر لینک از n8n یا محیط دیگری آمده، احتمالاً آن اجرا هنوز روی همین دیتابیس production ثبت نشده است.')
        return redirect('daily_off:dashboard')

    base_snapshots = run.snapshots.select_related('product').order_by('id')

    category = request.GET.get('category') or ''
    analysis_status = request.GET.get('analysis_status') or ''
    fetch_status = request.GET.get('fetch_status') or ''
    result_state = request.GET.get('result_state') or ''
    q = (request.GET.get('q') or '').strip()

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
    fetch_status_options = list(
        base_snapshots.exclude(fetch_status='')
        .order_by('fetch_status')
        .values_list('fetch_status', flat=True)
        .distinct()
    )

    run_counts = counts_for_queryset(base_snapshots)
    run_summary = {
        **compact_analysis_summary(run_counts),
        'total': base_snapshots.count(),
        'fetch_errors': base_snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR).count(),
    }

    snapshots = base_snapshots
    if category:
        snapshots = snapshots.filter(category_title=category)
    if analysis_status:
        snapshots = snapshots.filter(analysis_status=analysis_status)
    if fetch_status:
        snapshots = snapshots.filter(fetch_status=fetch_status)
    if result_state == 'has_result':
        snapshots = snapshots.filter(Q(product_url1__gt='') | Q(product_url2__gt='') | Q(product_url3__gt=''))
    elif result_state == 'no_result':
        snapshots = snapshots.filter(product_url1='', product_url2='', product_url3='')
    if q:
        search_filter = Q(title__icontains=q) | Q(vendor_name__icontains=q)
        if q.isdigit():
            search_filter |= Q(source_product_id=int(q)) | Q(id=int(q))
        snapshots = snapshots.filter(search_filter)

    return render(request, 'daily_off/run_detail.html', {
        'run': run,
        'snapshots': snapshots,
        'category_options': category_options,
        'status_options': status_options,
        'fetch_status_options': fetch_status_options,
        'selected_category': category,
        'selected_analysis_status': analysis_status,
        'selected_fetch_status': fetch_status,
        'selected_result_state': result_state,
        'q': q,
        'run_summary': run_summary,
        'shown_count': snapshots.count(),
    })


@require_POST
def delete_run(request, run_key):
    run = get_object_or_404(DailyRun, run_key=run_key)
    business_date = run.business_date
    snapshot_count = run.snapshots.count()
    run.delete()
    messages.success(request, f'اجرای {business_date} و {snapshot_count} اسنپ‌شات مربوط به آن حذف شد.')
    return redirect('daily_off:dashboard')


def product_detail(request, product_id):
    product = get_object_or_404(Product, basalam_product_id=product_id)
    snapshots = product.daily_snapshots.select_related('run').order_by('-business_date', '-captured_at')
    latest_snapshot = snapshots.first()
    latest_logs = latest_snapshot.analysis_logs.all()[:50] if latest_snapshot else []
    return render(request, 'daily_off/product_detail.html', {
        'product': product,
        'snapshots': snapshots,
        'latest_snapshot': latest_snapshot,
        'latest_logs': latest_logs,
    })
