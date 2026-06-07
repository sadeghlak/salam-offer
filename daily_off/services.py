from datetime import date

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import DailyProductSnapshot, DailyRun, Product


COUNT_UNITS = {'عددی', 'عدد', 'بسته', 'جفت'}
TERMINAL_ANALYSIS_STATUSES = {
    DailyProductSnapshot.AnalysisStatus.ANALYZED,
    DailyProductSnapshot.AnalysisStatus.NO_MATCH,
    DailyProductSnapshot.AnalysisStatus.ERROR,
}


def nested_get(data, path, default=''):
    current = data or {}
    for part in path.split('.'):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def as_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value, default=0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value):
    if isinstance(value, bool):
        return value
    if value in (1, '1', 'true', 'True', 'yes'):
        return True
    return False


def clean_string(value):
    if value in (None, False):
        return ''
    return str(value).strip()


def merge_config(existing, incoming):
    base = existing.copy() if isinstance(existing, dict) else {}
    if isinstance(incoming, dict):
        base.update(incoming)
    return base


def product_url(product_id, vendor_identifier=''):
    if vendor_identifier:
        return f'https://basalam.com/{vendor_identifier}/product/{product_id}'
    return f'https://basalam.com/product/{product_id}'


def attributes_text(raw_product):
    attrs = raw_product.get('attributes') or []
    parts = []
    for attr in attrs:
        key = attr.get('key') or attr.get('title') or ''
        value = attr.get('value') or ''
        if key and value:
            parts.append(f'{key}: {value}')
    return ' | '.join(parts)


def category_list_text(raw_product):
    categories = raw_product.get('category_list') or []
    return ' | '.join([item.get('title', '') for item in categories if item.get('title')])


def normalize_product(raw_product):
    product_id = as_int(raw_product.get('id') or raw_product.get('product_id'))
    vendor_identifier = nested_get(raw_product, 'vendor.identifier') or raw_product.get('vendor_identifier', '')
    unit_type = nested_get(raw_product, 'unit_type.name') or raw_product.get('product_unit_type', '')
    net_weight = as_float(raw_product.get('net_weight_decimal') or raw_product.get('net_weight') or raw_product.get('product_net_weight'))
    unit_quantity = as_float(raw_product.get('unit_quantity') or raw_product.get('product_unit_quantity'))

    if unit_type in COUNT_UNITS:
        weight_text = ' '.join([str(unit_quantity).rstrip('0').rstrip('.') if unit_quantity else '', unit_type]).strip()
    else:
        weight_text = ' '.join([str(net_weight).rstrip('0').rstrip('.') if net_weight else '', unit_type]).strip()

    return {
        'source_product_id': product_id,
        'title': raw_product.get('title') or raw_product.get('name') or raw_product.get('product_title_full', ''),
        'price': as_int(raw_product.get('price') or raw_product.get('product_price')),
        'primary_price': as_int(raw_product.get('primary_price') or raw_product.get('primaryPrice') or raw_product.get('product_primary_price')),
        'description': raw_product.get('description') or raw_product.get('product_description', ''),
        'summary': raw_product.get('summary') or raw_product.get('product_summary', ''),
        'photo_url': nested_get(raw_product, 'photo.original') or nested_get(raw_product, 'photo.lg') or raw_product.get('product_photo', ''),
        'product_status': nested_get(raw_product, 'status.name') or raw_product.get('product_status', ''),
        'inventory': as_int(raw_product.get('inventory') or raw_product.get('product_inventory')),
        'is_available': as_bool(raw_product.get('is_available') if 'is_available' in raw_product else raw_product.get('product_is_available')),
        'is_saleable': as_bool(raw_product.get('is_saleable') if 'is_saleable' in raw_product else raw_product.get('product_is_saleable')),
        'is_showable': as_bool(raw_product.get('is_showable') if 'is_showable' in raw_product else raw_product.get('product_is_showable')),
        'is_wholesale': as_bool(raw_product.get('is_wholesale') if 'is_wholesale' in raw_product else raw_product.get('product_is_wholesale')),
        'review_count': as_int(raw_product.get('review_count') or raw_product.get('product_review_count')),
        'rating': as_float(raw_product.get('rating') or raw_product.get('product_rating')),
        'preparation_day': as_int(raw_product.get('preparation_day') or raw_product.get('product_preparation_day')),
        'net_weight': net_weight,
        'packaged_weight': as_float(raw_product.get('packaged_weight') or raw_product.get('product_packaged_weight')),
        'unit_quantity': unit_quantity,
        'unit_type': unit_type,
        'weight_text': raw_product.get('product_weight_text') or weight_text,
        'category_title': nested_get(raw_product, 'category.title') or raw_product.get('product_category_title', ''),
        'category_parent_title': nested_get(raw_product, 'category.parent.title') or raw_product.get('product_category_parent_title', ''),
        'navigation_title': nested_get(raw_product, 'navigation.title') or nested_get(raw_product, 'category.title') or raw_product.get('product_navigation_title', ''),
        'navigation_slug': nested_get(raw_product, 'navigation.slug') or raw_product.get('product_navigation_slug', ''),
        'vendor_name': nested_get(raw_product, 'vendor.title') or nested_get(raw_product, 'vendor.name') or raw_product.get('vendor_name', ''),
        'vendor_identifier': vendor_identifier,
        'vendor_city': nested_get(raw_product, 'vendor.city.name') or raw_product.get('vendor_city', ''),
        'vendor_province': nested_get(raw_product, 'vendor.city.province.name') or raw_product.get('vendor_province', ''),
        'vendor_summary': nested_get(raw_product, 'vendor.summary') or raw_product.get('vendor_summary', ''),
        'vendor_status': nested_get(raw_product, 'vendor.status.name') or raw_product.get('vendor_status', ''),
        'attributes_text': raw_product.get('product_attributes_text') or attributes_text(raw_product),
        'category_list_text': raw_product.get('product_category_list_text') or category_list_text(raw_product),
        'raw_json': raw_product,
        'details_status': raw_product.get('details_status') or 'DETAILS_FETCHED',
        'status_row': raw_product.get('status_row') or DailyProductSnapshot.AnalysisStatus.PENDING,
    }


@transaction.atomic
def create_or_update_run(*, business_date=None, run_key=None, input_count=0, status=DailyRun.Status.RUNNING, config_json=None, notes=''):
    business_date = business_date or timezone.localdate()
    incoming_config = config_json or {}

    if run_key:
        run = DailyRun.objects.filter(run_key=run_key).first()
        if run is None:
            run = DailyRun.objects.filter(business_date=business_date).first()
        if run is None:
            run = DailyRun.objects.create(
                run_key=run_key,
                business_date=business_date,
                status=status,
                input_count=input_count,
                config_json=incoming_config,
                notes=notes,
                started_at=timezone.now(),
            )
            return run
    else:
        run = DailyRun.objects.filter(business_date=business_date).first()
        if run is None:
            run = DailyRun.objects.create(
                business_date=business_date,
                status=status,
                input_count=input_count,
                config_json=incoming_config,
                notes=notes,
                started_at=timezone.now(),
            )
            return run

    run.business_date = business_date
    run.status = status or run.status
    run.input_count = max(run.input_count or 0, input_count or 0)
    run.config_json = merge_config(run.config_json, incoming_config)
    if notes:
        run.notes = notes
    if run.started_at is None:
        run.started_at = timezone.now()
    if run.status not in {DailyRun.Status.COMPLETED, DailyRun.Status.PARTIAL_FAILED, DailyRun.Status.FAILED}:
        run.finished_at = None
    run.save(update_fields=['business_date', 'status', 'input_count', 'config_json', 'notes', 'started_at', 'finished_at', 'updated_at'])
    return run


@transaction.atomic
def store_product_snapshot(*, run, raw_product, business_date=None):
    business_date = business_date or run.business_date
    normalized = normalize_product(raw_product)
    product_id = normalized['source_product_id']
    if not product_id:
        raise ValueError('product_id is required')

    product, _ = Product.objects.update_or_create(
        basalam_product_id=product_id,
        defaults={
            'latest_title': normalized['title'],
            'latest_price': normalized['price'],
            'latest_primary_price': normalized['primary_price'],
            'latest_photo_url': normalized['photo_url'],
            'latest_vendor_identifier': normalized['vendor_identifier'],
            'latest_product_url': product_url(product_id, normalized['vendor_identifier']),
            'is_active': True,
        },
    )

    existing_snapshot = DailyProductSnapshot.objects.filter(run=run, source_product_id=product_id).first()
    preserved = {}
    if existing_snapshot:
        preserved = {
            'analysis_status': existing_snapshot.analysis_status,
            'status_row': existing_snapshot.status_row,
            'product_url1': existing_snapshot.product_url1,
            'product_url2': existing_snapshot.product_url2,
            'product_url3': existing_snapshot.product_url3,
            'accepted_candidates_count': existing_snapshot.accepted_candidates_count,
            'error_message': existing_snapshot.error_message,
        }

    snapshot_defaults = {
        'product': product,
        'business_date': business_date,
        'captured_at': timezone.now(),
        'fetch_status': DailyProductSnapshot.FetchStatus.DETAILS_FETCHED,
        'analysis_status': DailyProductSnapshot.AnalysisStatus.PENDING,
        'details_status': normalized.get('details_status') or 'DETAILS_FETCHED',
        'status_row': normalized.get('status_row') or DailyProductSnapshot.AnalysisStatus.PENDING,
        'error_message': '',
    }
    snapshot_defaults.update(normalized)
    if preserved:
        snapshot_defaults.update(preserved)

    snapshot, _ = DailyProductSnapshot.objects.update_or_create(
        run=run,
        source_product_id=product_id,
        defaults=snapshot_defaults,
    )

    refresh_run_status(run)
    return snapshot


@transaction.atomic
def mark_product_fetch_error(*, run, product_id, error_message, business_date=None):
    business_date = business_date or run.business_date
    product, _ = Product.objects.get_or_create(basalam_product_id=product_id)
    snapshot, _ = DailyProductSnapshot.objects.update_or_create(
        run=run,
        source_product_id=product_id,
        defaults={
            'product': product,
            'business_date': business_date,
            'fetch_status': DailyProductSnapshot.FetchStatus.FETCH_ERROR,
            'analysis_status': DailyProductSnapshot.AnalysisStatus.ERROR,
            'details_status': 'DETAILS_ERROR',
            'status_row': DailyProductSnapshot.AnalysisStatus.ERROR,
            'error_message': error_message,
        },
    )
    refresh_run_status(run)
    return snapshot


def analysis_counts_for_run(run):
    counts = {
        DailyProductSnapshot.AnalysisStatus.PENDING: 0,
        DailyProductSnapshot.AnalysisStatus.RUNNING: 0,
        DailyProductSnapshot.AnalysisStatus.ANALYZED: 0,
        DailyProductSnapshot.AnalysisStatus.NO_MATCH: 0,
        DailyProductSnapshot.AnalysisStatus.ERROR: 0,
    }
    rows = run.snapshots.values('analysis_status').annotate(total=Count('id'))
    for row in rows:
        counts[row['analysis_status']] = row['total']
    return counts


@transaction.atomic
def refresh_run_status(run, *, explicit_status=None, notes=None, finish=False):
    run.fetched_count = run.snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED).count()
    run.error_count = run.snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR).count()

    if notes is not None:
        run.notes = notes

    if explicit_status:
        run.status = explicit_status
    elif finish:
        total = run.snapshots.count()
        counts = analysis_counts_for_run(run)
        unfinished = counts[DailyProductSnapshot.AnalysisStatus.PENDING] + counts[DailyProductSnapshot.AnalysisStatus.RUNNING]
        error_total = run.error_count + counts[DailyProductSnapshot.AnalysisStatus.ERROR]

        if total and error_total >= total:
            run.status = DailyRun.Status.FAILED
        elif error_total:
            run.status = DailyRun.Status.PARTIAL_FAILED
        elif unfinished == 0:
            run.status = DailyRun.Status.COMPLETED
        else:
            run.status = DailyRun.Status.RUNNING

    if finish or run.status in {DailyRun.Status.COMPLETED, DailyRun.Status.PARTIAL_FAILED, DailyRun.Status.FAILED}:
        run.finished_at = timezone.now()

    run.save(update_fields=['fetched_count', 'error_count', 'status', 'notes', 'finished_at', 'updated_at'])
    return run


@transaction.atomic
def claim_pending_analysis(*, limit=100, run_key=None, business_date=None):
    limit = max(1, min(as_int(limit, 100), 100))
    queryset = DailyProductSnapshot.objects.filter(
        fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED,
        analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING,
    )
    if run_key:
        queryset = queryset.filter(run__run_key=run_key)
    else:
        business_date = business_date or timezone.localdate()
        queryset = queryset.filter(business_date=business_date)

    snapshot_ids = list(queryset.order_by('id').values_list('id', flat=True)[:limit])
    if not snapshot_ids:
        return []

    DailyProductSnapshot.objects.filter(
        id__in=snapshot_ids,
        analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING,
    ).update(
        analysis_status=DailyProductSnapshot.AnalysisStatus.RUNNING,
        status_row=DailyProductSnapshot.AnalysisStatus.RUNNING,
        updated_at=timezone.now(),
    )

    return list(
        DailyProductSnapshot.objects.filter(
            id__in=snapshot_ids,
            analysis_status=DailyProductSnapshot.AnalysisStatus.RUNNING,
        ).select_related('run', 'product').order_by('id')
    )


def find_snapshot(*, snapshot_id=None, run_key=None, product_id=None):
    queryset = DailyProductSnapshot.objects.select_related('run', 'product')
    if snapshot_id:
        return queryset.get(id=snapshot_id)
    if run_key and product_id:
        return queryset.get(run__run_key=run_key, source_product_id=product_id)
    raise ValueError('snapshot_id or run_key/product_id is required')


@transaction.atomic
def store_analysis_result(*, snapshot_id=None, run_key=None, product_id=None, result=None):
    result = result or {}
    nested_result = result.get('result') if isinstance(result.get('result'), dict) else {}
    data = {**result, **nested_result}

    snapshot = find_snapshot(
        snapshot_id=snapshot_id or data.get('snapshot_id'),
        run_key=run_key or data.get('run_key'),
        product_id=product_id or data.get('product_id') or data.get('source_product_id'),
    )

    product_url1 = clean_string(data.get('product_url1'))
    product_url2 = clean_string(data.get('product_url2'))
    product_url3 = clean_string(data.get('product_url3'))
    accepted_count = as_int(data.get('accepted_candidates_count'), 0)
    has_result = bool(product_url1 or product_url2 or product_url3 or accepted_count > 0)

    requested_status = clean_string(data.get('analysis_status'))
    allowed_statuses = {
        DailyProductSnapshot.AnalysisStatus.ANALYZED,
        DailyProductSnapshot.AnalysisStatus.NO_MATCH,
        DailyProductSnapshot.AnalysisStatus.ERROR,
    }
    if requested_status in allowed_statuses:
        analysis_status = requested_status
    else:
        analysis_status = DailyProductSnapshot.AnalysisStatus.ANALYZED if has_result else DailyProductSnapshot.AnalysisStatus.NO_MATCH

    snapshot.product_url1 = product_url1
    snapshot.product_url2 = product_url2
    snapshot.product_url3 = product_url3
    snapshot.accepted_candidates_count = accepted_count
    snapshot.analysis_status = analysis_status
    snapshot.status_row = clean_string(data.get('status_row')) or analysis_status
    snapshot.error_message = clean_string(data.get('error_message')) if analysis_status == DailyProductSnapshot.AnalysisStatus.ERROR else ''
    snapshot.save(update_fields=[
        'product_url1',
        'product_url2',
        'product_url3',
        'accepted_candidates_count',
        'analysis_status',
        'status_row',
        'error_message',
        'updated_at',
    ])
    refresh_run_status(snapshot.run)
    return snapshot


@transaction.atomic
def mark_analysis_error(*, snapshot_id=None, run_key=None, product_id=None, error_message=''):
    snapshot = find_snapshot(snapshot_id=snapshot_id, run_key=run_key, product_id=product_id)
    snapshot.analysis_status = DailyProductSnapshot.AnalysisStatus.ERROR
    snapshot.status_row = DailyProductSnapshot.AnalysisStatus.ERROR
    snapshot.error_message = clean_string(error_message) or 'unknown analysis error'
    snapshot.save(update_fields=['analysis_status', 'status_row', 'error_message', 'updated_at'])
    refresh_run_status(snapshot.run)
    return snapshot
