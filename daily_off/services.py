from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import DailyProductSnapshot, DailyRun, Product


COUNT_UNITS = {'عددی', 'عدد', 'بسته', 'جفت'}


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
        'vendor_status': nested_get(raw_product, 'vendor.status.name') or raw_product.get('vendor_status', ''),
        'attributes_text': raw_product.get('product_attributes_text') or attributes_text(raw_product),
        'category_list_text': raw_product.get('product_category_list_text') or category_list_text(raw_product),
        'raw_json': raw_product,
    }


@transaction.atomic
def create_or_update_run(*, business_date=None, run_key=None, input_count=0, status=DailyRun.Status.RUNNING, config_json=None, notes=''):
    business_date = business_date or date.today()
    defaults = {
        'business_date': business_date,
        'status': status,
        'input_count': input_count,
        'config_json': config_json or {},
        'notes': notes,
        'started_at': timezone.now(),
    }
    if run_key:
        run, _ = DailyRun.objects.update_or_create(run_key=run_key, defaults=defaults)
    else:
        run = DailyRun.objects.create(**defaults)
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

    snapshot_defaults = {
        'product': product,
        'business_date': business_date,
        'captured_at': timezone.now(),
        'fetch_status': DailyProductSnapshot.FetchStatus.DETAILS_FETCHED,
        'analysis_status': DailyProductSnapshot.AnalysisStatus.PENDING,
        'error_message': '',
    }
    snapshot_defaults.update(normalized)

    snapshot, _ = DailyProductSnapshot.objects.update_or_create(
        run=run,
        source_product_id=product_id,
        defaults=snapshot_defaults,
    )

    run.fetched_count = run.snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED).count()
    run.error_count = run.snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR).count()
    run.save(update_fields=['fetched_count', 'error_count', 'updated_at'])
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
            'error_message': error_message,
        },
    )
    run.error_count = run.snapshots.filter(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR).count()
    run.save(update_fields=['error_count', 'updated_at'])
    return snapshot
