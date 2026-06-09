import re
from dataclasses import dataclass


BASE_WEIGHT_UNIT = 'گرم'
BASE_LENGTH_UNIT = 'سانتی‌متر'
BASE_COUNT_UNIT = 'عددی'
TOLERANCE_PERCENT = 1

UNIT_ALIASES = {
    'عددی': 'عددی',
    'عدد': 'عددی',
    'کیلوگرم': 'کیلوگرم',
    'کیلو گرم': 'کیلوگرم',
    'كيلوگرم': 'کیلوگرم',
    'كيلو گرم': 'کیلوگرم',
    'کیلو': 'کیلوگرم',
    'كيلو': 'کیلوگرم',
    'kg': 'کیلوگرم',
    'گرم': 'گرم',
    'g': 'گرم',
    'متر': 'متر',
    'meter': 'متر',
    'سانتی‌متر': 'سانتی‌متر',
    'سانتی متر': 'سانتی‌متر',
    'سانتیمتر': 'سانتی‌متر',
    'cm': 'سانتی‌متر',
    'مثقال': 'مثقال',
}

UNIT_GROUPS = {
    'عددی': 'count',
    'کیلوگرم': 'weight',
    'گرم': 'weight',
    'مثقال': 'weight',
    'متر': 'length',
    'سانتی‌متر': 'length',
}

UNIT_TO_BASE_MULTIPLIER = {
    'عددی': 1,
    'کیلوگرم': 1000,
    'گرم': 1,
    'مثقال': 4.608,
    'متر': 100,
    'سانتی‌متر': 1,
}

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
UNIT_PATTERN = '|'.join(sorted([re.escape(unit) for unit in UNIT_ALIASES], key=len, reverse=True))
TITLE_MEASUREMENT_RE = re.compile(rf'(\d+(?:\.\d+)?)\s*({UNIT_PATTERN})(?:ی|ى)?')


@dataclass
class NormalizedMeasurement:
    raw_unit: str = ''
    canonical_unit: str = ''
    group: str = ''
    normalized_quantity: float | None = None
    basis: str = 'missing'
    confidence: str = 'missing'
    title_unit: str = ''
    title_group: str = ''
    title_normalized_quantity: float | None = None
    title_basis: str = 'missing'
    title_confidence: str = 'missing'


@dataclass
class UnitComparison:
    source: NormalizedMeasurement
    candidate: NormalizedMeasurement
    comparable: bool
    equivalent: bool
    score: float
    reasons: list
    title_measurement_used: bool = False
    title_measurement_confidence: str = ''


def normalize_text(value):
    return str(value or '').translate(PERSIAN_DIGITS).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').strip().lower()


def as_float(value):
    try:
        if value in (None, ''):
            return 0
        return float(str(value).translate(PERSIAN_DIGITS))
    except (TypeError, ValueError):
        return 0


def canonical_unit(value):
    normalized = normalize_text(value)
    return UNIT_ALIASES.get(normalized, normalized if normalized in UNIT_GROUPS else '')


def group_for_unit(unit):
    return UNIT_GROUPS.get(canonical_unit(unit), '')


def to_base_quantity(quantity, unit):
    canonical = canonical_unit(unit)
    if not canonical:
        return None
    value = as_float(quantity)
    if value <= 0:
        return None
    return value * UNIT_TO_BASE_MULTIPLIER[canonical]


def extract_title_measurement(title):
    normalized = normalize_text(title)
    for match in TITLE_MEASUREMENT_RE.finditer(normalized):
        quantity = as_float(match.group(1))
        unit = canonical_unit(match.group(2))
        if quantity > 0 and unit:
            return unit, quantity, to_base_quantity(quantity, unit)
    return '', 0, None


def normalize_measurement(*, unit_type='', unit_quantity=0, net_weight=0, title=''):
    canonical = canonical_unit(unit_type)
    group = group_for_unit(canonical)
    basis = 'missing'
    normalized_quantity = None

    if canonical == 'عددی':
        normalized_quantity = as_float(unit_quantity) or 1
        basis = 'official_unit_quantity'
    elif group == 'weight':
        quantity = as_float(net_weight) if canonical in {'گرم', 'کیلوگرم', 'مثقال'} else 0
        if not quantity:
            quantity = as_float(unit_quantity)
        normalized_quantity = to_base_quantity(quantity, canonical)
        basis = 'official_net_weight' if as_float(net_weight) else 'official_unit_quantity'
    elif group == 'length':
        quantity = as_float(unit_quantity) or as_float(net_weight)
        normalized_quantity = to_base_quantity(quantity, canonical)
        basis = 'official_unit_quantity'

    title_unit, title_quantity, title_normalized = extract_title_measurement(title)
    title_group = group_for_unit(title_unit)

    if not normalized_quantity and title_normalized:
        canonical = title_unit
        group = title_group
        normalized_quantity = title_normalized
        basis = 'title_extracted'

    confidence = 'high' if basis.startswith('official') else 'low' if basis == 'title_extracted' else 'missing'
    return NormalizedMeasurement(
        raw_unit=str(unit_type or ''),
        canonical_unit=canonical,
        group=group,
        normalized_quantity=normalized_quantity,
        basis=basis,
        confidence=confidence,
        title_unit=title_unit,
        title_group=title_group,
        title_normalized_quantity=title_normalized,
        title_basis='title_extracted' if title_normalized else 'missing',
        title_confidence='low' if title_normalized else 'missing',
    )


def quantities_equivalent(source_quantity, candidate_quantity, tolerance_percent=TOLERANCE_PERCENT):
    if not source_quantity or not candidate_quantity:
        return False
    tolerance = abs(source_quantity) * (tolerance_percent / 100)
    return abs(source_quantity - candidate_quantity) <= tolerance


def compare_measurements(source, candidate, tolerance_percent=TOLERANCE_PERCENT):
    reasons = []
    title_used = source.basis == 'title_extracted' or candidate.basis == 'title_extracted'
    title_confidence = 'low' if title_used or source.title_normalized_quantity or candidate.title_normalized_quantity else ''

    if not source.group or not candidate.group or not source.normalized_quantity or not candidate.normalized_quantity:
        reasons.append('unit_missing')
        return UnitComparison(source, candidate, False, False, 0, reasons, title_used, title_confidence)

    if source.group != candidate.group:
        reasons.append('unit_group_mismatch')
        return UnitComparison(source, candidate, False, False, 0, reasons, title_used, title_confidence)

    equivalent = quantities_equivalent(source.normalized_quantity, candidate.normalized_quantity, tolerance_percent)
    if not equivalent:
        reasons.append('unit_quantity_mismatch')
    return UnitComparison(source, candidate, True, equivalent, 1 if equivalent else 0, reasons, title_used, title_confidence)
