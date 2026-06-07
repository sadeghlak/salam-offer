import json
import math
import mimetypes
import re
import uuid
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .models import AnalysisStatusLog, DailyProductSnapshot
from .services import as_float, as_int, clean_string, log_analysis_status, nested_get, product_url


COUNT_UNITS = {'عددی', 'عدد', 'بسته', 'جفت'}
WEIGHT_UNITS = {'گرم', 'کیلوگرم', 'کیلو گرم', 'kg', 'g'}


@dataclass
class AnalysisConfig:
    text_search_size: int = settings.CHEAPER_ANALYSIS_TEXT_SEARCH_SIZE
    image_search_size: int = settings.CHEAPER_ANALYSIS_IMAGE_SEARCH_SIZE
    detail_fetch_limit: int = settings.CHEAPER_ANALYSIS_DETAIL_FETCH_LIMIT
    min_similarity: float = settings.CHEAPER_ANALYSIS_MIN_SIMILARITY
    min_cheaper_delta: int = settings.CHEAPER_ANALYSIS_MIN_CHEAPER_DELTA
    request_timeout_seconds: float = settings.CHEAPER_ANALYSIS_REQUEST_TIMEOUT_SECONDS
    enable_image_search: bool = settings.CHEAPER_ANALYSIS_ENABLE_IMAGE_SEARCH
    score_weights: dict = field(default_factory=lambda: settings.CHEAPER_ANALYSIS_SCORE_WEIGHTS.copy())


@dataclass
class CandidateResult:
    candidate_id: int
    title: str
    price: int
    vendor_identifier: str
    url: str
    similarity_score: float
    embedding_score: float
    category_score: float
    weight_score: float
    is_exact_weight_match: bool
    price_gap: int
    price_gap_percent: float
    search_sources: list
    accepted: bool


@dataclass
class AnalysisResult:
    snapshot_id: int
    product_id: int
    product_url1: str = ''
    product_url2: str = ''
    product_url3: str = ''
    accepted_candidates_count: int = 0
    analysis_status: str = DailyProductSnapshot.AnalysisStatus.NO_MATCH
    status_row: str = DailyProductSnapshot.AnalysisStatus.NO_MATCH
    candidates_seen_count: int = 0
    candidates_deduped_count: int = 0
    candidate_details_fetched_count: int = 0
    accepted_candidates: list = field(default_factory=list)
    rejected_candidates: list = field(default_factory=list)

    def to_payload(self):
        return {
            'snapshot_id': self.snapshot_id,
            'product_id': self.product_id,
            'product_url1': self.product_url1,
            'product_url2': self.product_url2,
            'product_url3': self.product_url3,
            'accepted_candidates_count': self.accepted_candidates_count,
            'analysis_status': self.analysis_status,
            'status_row': self.status_row,
            'candidates_seen_count': self.candidates_seen_count,
            'candidates_deduped_count': self.candidates_deduped_count,
            'candidate_details_fetched_count': self.candidate_details_fetched_count,
        }


def normalize_text(value):
    text = str(value or '')
    text = re.sub(r'[أإآ]', 'ا', text)
    text = text.replace('ي', 'ی').replace('ك', 'ک')
    text = re.sub(r'[‌‏\x00-\x1f\x7f]+', ' ', text)
    text = re.sub(r'[^\w\s؀-ۿ]+', ' ', text, flags=re.UNICODE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def tokenize(value):
    return [token for token in normalize_text(value).split(' ') if len(token) > 1]


def cosine_token_similarity(left, right):
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0

    left_freq = {}
    right_freq = {}
    for token in left_tokens:
        left_freq[token] = left_freq.get(token, 0) + 1
    for token in right_tokens:
        right_freq[token] = right_freq.get(token, 0) + 1

    vocab = set(left_freq) | set(right_freq)
    dot = sum(left_freq.get(token, 0) * right_freq.get(token, 0) for token in vocab)
    left_norm = sum(value * value for value in left_freq.values())
    right_norm = sum(value * value for value in right_freq.values())
    if not left_norm or not right_norm:
        return 0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def normalize_unit(value):
    return normalize_text(value)


def source_dict(snapshot):
    return {
        'source_product_id': snapshot.source_product_id,
        'source_title': snapshot.title,
        'source_price': snapshot.price,
        'source_photo': snapshot.photo_url,
        'source_category_title': snapshot.category_title,
        'source_category_parent_title': snapshot.category_parent_title,
        'source_navigation_slug': snapshot.navigation_slug,
        'source_weight': snapshot.net_weight,
        'source_unit_quantity': snapshot.unit_quantity,
        'source_unit_type': snapshot.unit_type,
        'source_attributes_text': snapshot.attributes_text,
        'source_description': snapshot.description,
    }


def category_score(snapshot, candidate):
    source_slug = normalize_text(snapshot.navigation_slug or snapshot.category_title)
    candidate_slug = normalize_text(candidate.get('candidate_navigation_slug') or candidate.get('candidate_category_title'))
    source_title = normalize_text(snapshot.category_title)
    candidate_title = normalize_text(candidate.get('candidate_category_title'))
    source_parent = normalize_text(snapshot.category_parent_title)
    candidate_parent = normalize_text(candidate.get('candidate_category_parent_title'))
    if source_slug and candidate_slug and source_slug == candidate_slug:
        return 1
    if source_title and candidate_title and source_title == candidate_title:
        return 0.9
    if source_parent and candidate_parent and source_parent == candidate_parent:
        return 0.55
    return 0


def exact_weight_match(snapshot, candidate):
    source_unit = normalize_unit(snapshot.unit_type)
    candidate_unit = normalize_unit(candidate.get('candidate_unit_type'))
    if not source_unit or not candidate_unit or source_unit != candidate_unit:
        return False

    if source_unit in COUNT_UNITS:
        source_qty = as_float(snapshot.unit_quantity)
        candidate_qty = as_float(candidate.get('candidate_unit_quantity'))
        return bool(source_qty and candidate_qty and source_qty == candidate_qty)

    if source_unit in WEIGHT_UNITS:
        source_weight = as_float(snapshot.net_weight)
        candidate_weight = as_float(candidate.get('candidate_net_weight'))
        return bool(source_weight and candidate_weight and source_weight == candidate_weight)

    source_qty = as_float(snapshot.unit_quantity or snapshot.net_weight)
    candidate_qty = as_float(candidate.get('candidate_unit_quantity') or candidate.get('candidate_net_weight'))
    return bool(source_qty and candidate_qty and source_qty == candidate_qty)


def http_json_get(url, *, timeout):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'SalamOffer/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return json.loads(body or '{}')
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code} from {url}') from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'failed to fetch JSON from {url}: {exc}') from exc


def http_bytes_get(url, *, timeout):
    request = Request(url, headers={'User-Agent': 'SalamOffer/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get('Content-Type') or mimetypes.guess_type(url)[0] or 'application/octet-stream'
            return response.read(), content_type
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code} while downloading image') from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f'failed to download image: {exc}') from exc


def http_multipart_file_post(url, *, field_name, filename, content, content_type, timeout):
    boundary = f'----SalamOfferBoundary{uuid.uuid4().hex}'
    body = b''.join([
        f'--{boundary}\r\n'.encode(),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode(),
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        content,
        b'\r\n',
        f'--{boundary}--\r\n'.encode(),
    ])
    request = Request(
        url,
        data=body,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Accept': 'application/json',
            'User-Agent': 'SalamOffer/1.0',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8') or '{}')
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code} from image search') from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'failed image search: {exc}') from exc


def extract_products(body):
    if isinstance(body.get('products'), list):
        return body['products']
    result = body.get('result') or {}
    if isinstance(result.get('products'), list):
        return result['products']
    return []


def normalize_search_product(product, *, snapshot, source_name, rank):
    base = source_dict(snapshot)
    return {
        **base,
        'candidate_id': as_int(product.get('id')),
        'candidate_title': product.get('name') or product.get('title') or '',
        'candidate_price': as_int(product.get('price')),
        'candidate_primary_price': as_int(product.get('primaryPrice') or product.get('primary_price')),
        'candidate_photo': nested_get(product, 'photo.original') or nested_get(product, 'photo.LARGE') or nested_get(product, 'photo.MEDIUM') or nested_get(product, 'photo.SMALL'),
        'candidate_category_title': product.get('categoryTitle') or nested_get(product, 'category.title'),
        'candidate_category_parent_title': nested_get(product, 'category.parent.title'),
        'candidate_navigation_slug': nested_get(product, 'navigation.slug'),
        'candidate_weight': as_float(product.get('weight')),
        'candidate_vendor_name': nested_get(product, 'vendor.name'),
        'candidate_vendor_identifier': nested_get(product, 'vendor.identifier'),
        'candidate_vendor_city': nested_get(product, 'vendor.owner.city'),
        'candidate_vendor_status': nested_get(product, 'vendor.status.title'),
        'search_source': source_name,
        'search_rank': rank,
    }


def search_by_text(snapshot, config):
    query = urlencode({
        'q': snapshot.title,
        'from': 0,
        'size': config.text_search_size,
        'dynamicFacets': 'false',
        'grouped': 'false',
        'adsImpressionDisable': 'true',
        'enableNavigations': 'false',
    })
    body = http_json_get(f'{settings.BASALAM_TEXT_SEARCH_URL}?{query}', timeout=config.request_timeout_seconds)
    products = extract_products(body)[:config.text_search_size]
    return [normalize_search_product(product, snapshot=snapshot, source_name='text', rank=index + 1) for index, product in enumerate(products)]


def search_by_image(snapshot, config):
    if not config.enable_image_search or not snapshot.photo_url:
        return []
    content, content_type = http_bytes_get(snapshot.photo_url, timeout=config.request_timeout_seconds)
    body = http_multipart_file_post(
        settings.BASALAM_IMAGE_SEARCH_URL,
        field_name='file',
        filename=f'{snapshot.source_product_id}.jpg',
        content=content,
        content_type=content_type,
        timeout=config.request_timeout_seconds,
    )
    products = extract_products(body)[:config.image_search_size]
    return [normalize_search_product(product, snapshot=snapshot, source_name='image', rank=index + 1) for index, product in enumerate(products)]


def dedupe_candidates(*, source_snapshot, text_results, image_results, detail_fetch_limit):
    mapped = {}
    for item in [*text_results, *image_results]:
        candidate_id = as_int(item.get('candidate_id'))
        if not candidate_id or candidate_id == source_snapshot.source_product_id:
            continue
        if candidate_id not in mapped:
            row = item.copy()
            row['search_sources'] = [item.get('search_source')]
            mapped[candidate_id] = row
            continue
        existing = mapped[candidate_id]
        existing['search_sources'] = sorted(set([*(existing.get('search_sources') or []), item.get('search_source')]))
        for key in ['candidate_title', 'candidate_photo', 'candidate_price', 'candidate_weight', 'candidate_vendor_identifier']:
            if not existing.get(key) and item.get(key):
                existing[key] = item[key]
    return list(mapped.values())[:detail_fetch_limit]


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


def normalize_candidate_detail(raw, fallback=None):
    fallback = fallback or {}
    unit_type = nested_get(raw, 'unit_type.name') or ''
    normalized_unit = normalize_unit(unit_type)
    if normalized_unit in COUNT_UNITS:
        candidate_weight_text = ' '.join([clean_string(raw.get('unit_quantity')), unit_type]).strip()
    else:
        candidate_weight_text = ' '.join([clean_string(raw.get('net_weight_decimal') or raw.get('net_weight')), unit_type]).strip()

    return {
        **fallback,
        'candidate_id': as_int(raw.get('id') or fallback.get('candidate_id')),
        'candidate_title': raw.get('title') or fallback.get('candidate_title', ''),
        'candidate_price': as_int(raw.get('price') or fallback.get('candidate_price')),
        'candidate_primary_price': as_int(raw.get('primary_price') or fallback.get('candidate_primary_price')),
        'candidate_description': raw.get('description') or '',
        'candidate_summary': raw.get('summary') or '',
        'candidate_photo': nested_get(raw, 'photo.original') or nested_get(raw, 'photo.lg') or fallback.get('candidate_photo', ''),
        'candidate_category_title': nested_get(raw, 'category.title') or fallback.get('candidate_category_title', ''),
        'candidate_category_parent_title': nested_get(raw, 'category.parent.title') or fallback.get('candidate_category_parent_title', ''),
        'candidate_navigation_title': nested_get(raw, 'navigation.title') or nested_get(raw, 'category.title') or '',
        'candidate_navigation_slug': nested_get(raw, 'navigation.slug') or fallback.get('candidate_navigation_slug', ''),
        'candidate_net_weight': as_float(raw.get('net_weight_decimal') or raw.get('net_weight') or fallback.get('candidate_weight')),
        'candidate_packaged_weight': as_float(raw.get('packaged_weight')),
        'candidate_unit_quantity': as_float(raw.get('unit_quantity')),
        'candidate_unit_type': unit_type,
        'candidate_weight_text': candidate_weight_text,
        'candidate_vendor_name': nested_get(raw, 'vendor.title') or nested_get(raw, 'vendor.name') or fallback.get('candidate_vendor_name', ''),
        'candidate_vendor_identifier': nested_get(raw, 'vendor.identifier') or fallback.get('candidate_vendor_identifier', ''),
        'candidate_vendor_city': nested_get(raw, 'vendor.city.name') or fallback.get('candidate_vendor_city', ''),
        'candidate_vendor_province': nested_get(raw, 'vendor.city.province.name'),
        'candidate_vendor_status': nested_get(raw, 'vendor.status.name') or fallback.get('candidate_vendor_status', ''),
        'candidate_rating': as_float(raw.get('rating')),
        'candidate_review_count': as_int(raw.get('review_count')),
        'candidate_attributes_text': attributes_text(raw),
        'candidate_category_list_text': category_list_text(raw),
        'search_sources': fallback.get('search_sources') or [],
    }


def fetch_candidate_detail(candidate, config):
    candidate_id = as_int(candidate.get('candidate_id'))
    url = settings.BASALAM_PRODUCT_DETAIL_URL_TEMPLATE.format(product_id=candidate_id)
    body = http_json_get(url, timeout=config.request_timeout_seconds)
    return normalize_candidate_detail(body, fallback=candidate)


def score_candidate(*, snapshot, candidate, config):
    source_text = ' | '.join([
        clean_string(snapshot.title), clean_string(snapshot.description), clean_string(snapshot.category_title),
        clean_string(snapshot.category_parent_title), clean_string(snapshot.attributes_text), clean_string(snapshot.unit_type),
        clean_string(snapshot.unit_quantity), clean_string(snapshot.net_weight),
    ])
    candidate_text = ' | '.join([
        clean_string(candidate.get('candidate_title')), clean_string(candidate.get('candidate_description')),
        clean_string(candidate.get('candidate_category_title')), clean_string(candidate.get('candidate_category_parent_title')),
        clean_string(candidate.get('candidate_attributes_text')), clean_string(candidate.get('candidate_unit_type')),
        clean_string(candidate.get('candidate_unit_quantity')), clean_string(candidate.get('candidate_net_weight')),
    ])
    embedding_score = cosine_token_similarity(source_text, candidate_text)
    cat_score = category_score(snapshot, candidate)
    is_exact = exact_weight_match(snapshot, candidate)
    weight_score = 1 if is_exact else 0
    weights = config.score_weights
    final_score = max(0, min(1, embedding_score * weights['embedding'] + cat_score * weights['category'] + weight_score * weights['weight']))
    candidate_price = as_int(candidate.get('candidate_price'))
    price_gap = snapshot.price - candidate_price
    price_gap_percent = (price_gap / snapshot.price * 100) if snapshot.price else 0
    is_cheaper = candidate_price > 0 and price_gap >= config.min_cheaper_delta
    accepted = is_cheaper and final_score >= config.min_similarity and is_exact
    candidate_id = as_int(candidate.get('candidate_id'))
    vendor_identifier = clean_string(candidate.get('candidate_vendor_identifier'))

    return CandidateResult(
        candidate_id=candidate_id,
        title=clean_string(candidate.get('candidate_title')),
        price=candidate_price,
        vendor_identifier=vendor_identifier,
        url=product_url(candidate_id, vendor_identifier) if candidate_id else '',
        similarity_score=round(final_score, 4),
        embedding_score=round(embedding_score, 4),
        category_score=round(cat_score, 4),
        weight_score=round(weight_score, 4),
        is_exact_weight_match=is_exact,
        price_gap=price_gap,
        price_gap_percent=round(price_gap_percent, 2),
        search_sources=candidate.get('search_sources') or [],
        accepted=accepted,
    )


def aggregate_candidate_results(*, snapshot, scored, candidates_seen_count, candidates_deduped_count, detail_count):
    accepted = [row for row in scored if row.accepted]
    accepted.sort(key=lambda row: (-row.similarity_score, row.price))
    top_matches = accepted[:3]
    urls = [row.url for row in top_matches]
    return AnalysisResult(
        snapshot_id=snapshot.id,
        product_id=snapshot.source_product_id,
        product_url1=urls[0] if len(urls) > 0 else '',
        product_url2=urls[1] if len(urls) > 1 else '',
        product_url3=urls[2] if len(urls) > 2 else '',
        accepted_candidates_count=len(accepted),
        analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED if accepted else DailyProductSnapshot.AnalysisStatus.NO_MATCH,
        status_row=DailyProductSnapshot.AnalysisStatus.ANALYZED if accepted else DailyProductSnapshot.AnalysisStatus.NO_MATCH,
        candidates_seen_count=candidates_seen_count,
        candidates_deduped_count=candidates_deduped_count,
        candidate_details_fetched_count=detail_count,
        accepted_candidates=accepted,
        rejected_candidates=[row for row in scored if not row.accepted][:20],
    )


def candidate_log_rows(rows):
    return [
        {
            'candidate_id': row.candidate_id,
            'title': row.title,
            'price': row.price,
            'similarity_score': row.similarity_score,
            'embedding_score': row.embedding_score,
            'category_score': row.category_score,
            'weight_score': row.weight_score,
            'is_exact_weight_match': row.is_exact_weight_match,
            'price_gap': row.price_gap,
            'accepted': row.accepted,
            'search_sources': row.search_sources,
        }
        for row in rows
    ]


def analyze_snapshot(snapshot, *, config=None, request_id='', actor='django_analysis'):
    config = config or AnalysisConfig()
    log_analysis_status(snapshot=snapshot, event_type=AnalysisStatusLog.EventType.STARTED, message='تحلیل محصول شروع شد.', request_id=request_id, actor=actor)
    log_analysis_status(snapshot=snapshot, event_type=AnalysisStatusLog.EventType.SEARCH_STARTED, message='جستجوی محصولات مشابه شروع شد.', request_id=request_id, actor=actor)

    text_results = search_by_text(snapshot, config)
    log_analysis_status(
        snapshot=snapshot,
        event_type=AnalysisStatusLog.EventType.TEXT_SEARCH_COMPLETED,
        message='جستجوی متنی کامل شد.',
        metadata={'result_count': len(text_results)},
        request_id=request_id,
        actor=actor,
    )

    try:
        image_results = search_by_image(snapshot, config)
        image_event = AnalysisStatusLog.EventType.IMAGE_SEARCH_COMPLETED if image_results else AnalysisStatusLog.EventType.IMAGE_SEARCH_SKIPPED
        log_analysis_status(
            snapshot=snapshot,
            event_type=image_event,
            message='جستجوی تصویری کامل شد.' if image_results else 'جستجوی تصویری نتیجه‌ای نداشت یا عکس موجود نبود.',
            metadata={'result_count': len(image_results), 'enabled': config.enable_image_search, 'has_photo': bool(snapshot.photo_url)},
            request_id=request_id,
            actor=actor,
        )
    except Exception as exc:
        image_results = []
        log_analysis_status(
            snapshot=snapshot,
            event_type=AnalysisStatusLog.EventType.IMAGE_SEARCH_SKIPPED,
            message=f'جستجوی تصویری به دلیل خطا رد شد: {exc}',
            metadata={'error': str(exc)},
            request_id=request_id,
            actor=actor,
        )

    deduped = dedupe_candidates(
        source_snapshot=snapshot,
        text_results=text_results,
        image_results=image_results,
        detail_fetch_limit=config.detail_fetch_limit,
    )
    log_analysis_status(
        snapshot=snapshot,
        event_type=AnalysisStatusLog.EventType.CANDIDATES_DEDUPED,
        message='کاندیداهای مشابه یکتا شدند.',
        metadata={'raw_count': len(text_results) + len(image_results), 'deduped_count': len(deduped)},
        request_id=request_id,
        actor=actor,
    )

    detailed = []
    for candidate in deduped:
        try:
            detailed.append(fetch_candidate_detail(candidate, config))
        except Exception as exc:
            log_analysis_status(
                snapshot=snapshot,
                event_type=AnalysisStatusLog.EventType.ERROR,
                message=f'خطای دریافت جزئیات کاندیدا {candidate.get("candidate_id")}: {exc}',
                metadata={'candidate_id': candidate.get('candidate_id'), 'retryable': False},
                request_id=request_id,
                actor=actor,
            )

    scored = [score_candidate(snapshot=snapshot, candidate=candidate, config=config) for candidate in detailed]
    result = aggregate_candidate_results(
        snapshot=snapshot,
        scored=scored,
        candidates_seen_count=len(text_results) + len(image_results),
        candidates_deduped_count=len(deduped),
        detail_count=len(detailed),
    )
    log_analysis_status(
        snapshot=snapshot,
        event_type=AnalysisStatusLog.EventType.CANDIDATES_SCORED,
        message='امتیازدهی کاندیداها کامل شد.',
        metadata={
            'scored_count': len(scored),
            'accepted_candidates_count': result.accepted_candidates_count,
            'top_candidates': candidate_log_rows(result.accepted_candidates[:10]),
            'top_rejected_candidates': candidate_log_rows(result.rejected_candidates[:10]),
        },
        request_id=request_id,
        actor=actor,
    )
    return result
