import re
from dataclasses import dataclass, field

from .family_router import route_product_family
from .semantic_rules import extract_cues, normalize_for_tokens, normalize_text
from .unit_rules import normalize_measurement


NOISE_PATTERNS = [
    r'ارسال\s*رایگان',
    r'فروش\s*ویژه',
    r'تخفیف(?:\s*دار)?',
    r'قیمت\s*عمده',
    r'قیمت\s*ویژه',
    r'خرید\s*مستقیم',
    r'مستقیم\s*از\s*تولید\s*کننده',
    r'مستقیم\s*از\s*زنبوردار',
    r'تضمین\s*کیفیت',
    r'ضمانت\s*کیفیت',
    r'ضمانت\s*اصالت',
    r'با\s*گارانتی',
    r'گارانتی\s*\S+',
    r'پس\s*کرایه',
    r'اورجینال',
    r'اصلی',
    r'اصل',
    r'درجه\s*یک',
    r'اعلا',
    r'ممتاز',
]

STOP_TOKENS = {
    'محصول', 'مدل', 'طرح', 'کد', 'برای', 'مناسب', 'دارای', 'همراه', 'بدون', 'رایگان', 'ارسال',
    'تضمین', 'کیفیت', 'قیمت', 'ویژه', 'تخفیف', 'اصلی', 'اصل', 'اورجینال', 'فروش', 'خرید',
    'مستقیم', 'تولید', 'کننده', 'فروشنده', 'جدید', 'تازه', 'درجه', 'اعلا', 'ممتاز', 'عدد',
    'عددی', 'بسته', 'پک', 'رنگ', 'رنگی', 'باکیفیت', 'بالا', 'فوری', 'پس', 'کرایه',
}

PRODUCT_TYPE_PATTERNS = {
    'چادر مسافرتی': [r'چادر\s*مسافرتی'],
    'میز ناهار خوری': [r'میز\s*ناهار\s*خوری'],
    'سرویس قاشق و چنگال': [r'سرویس\s*قاشق\s*و\s*چنگال'],
    'ماشین ظرفشویی': [r'ماشین\s*ظرفشویی'],
    'ماشین لباسشویی': [r'ماشین\s*لباسشویی'],
    'سرخ کن': [r'سرخ\s*کن'],
    'خشک کن': [r'خشک\s*کن'],
    'هارد اکسترنال': [r'هارد\s*اکسترنال', r'هارداکسترنال'],
    'گوشی موبایل': [r'گوشی\s*موبایل', r'موبایل'],
    'ایرپاد': [r'ایرپاد', r'هندزفری\s*(?:بی\s*سیم|بلوتوثی)'],
    'ماهی': [r'ماهی'],
    'برنج': [r'برنج'],
    'فلفل': [r'فلفل'],
    'آرد': [r'آرد'],
    'کره': [r'کره'],
    'روغن': [r'روغن'],
    'عسل': [r'عسل'],
    'شربت': [r'شربت'],
    'گوشت': [r'گوشت'],
    'حبوبات': [r'لوبیا|نخود|ماش|لپه'],
    'کرم': [r'کرم'],
    'کیف': [r'کیف'],
    'شلف': [r'شلف'],
    'ماساژور': [r'ماساژور'],
    'شلوار': [r'شلوار'],
}

FOOD_INGREDIENT_PATTERNS = {
    'نارگیل': [r'نارگیل'],
    'بادام زمینی': [r'بادام\s*زمینی'],
    'جو دوسر': [r'جو\s*دوسر', r'جودوسر'],
    'گندم': [r'گندم'],
    'کنجد': [r'کنجد'],
    'کلزا': [r'کلزا'],
    'سویا': [r'سویا'],
    'نخود': [r'نخود'],
    'ماش': [r'ماش'],
    'لوبیا چشم بلبلی': [r'لوبیا\s*چشم\s*بلبلی'],
    'بوقلمون': [r'بوقلمون'],
    'مخلوط': [r'مخلوط'],
}

FOOD_VARIETY_PATTERNS = {
    'فلفل سیاه': [r'فلفل\s*سیاه'],
    'فلفل قرمز': [r'فلفل\s*قرمز'],
    'هاشمی': [r'هاشمی'],
    'طارم': [r'طارم'],
    'فجر': [r'فجر'],
    'عنبربو': [r'عنبربو'],
    'شیرودی': [r'شیرودی'],
    'ندا': [r'\bندا\b'],
    'صدری': [r'صدری'],
    'سرخو': [r'سرخو'],
    'شیر': [r'ماهی\s*شیر'],
    'طلال': [r'طلال'],
    'خنو': [r'خنو'],
    'مقوا': [r'مقوا'],
    'هوور': [r'هوور'],
    'حسون': [r'حسون'],
    'عناب': [r'عناب'],
    'آویشن': [r'آویشن'],
    'چهل گیاه': [r'چهل\s*گیاه', r'40\s*گیاه'],
    'چند گیاه': [r'چند\s*گیاه'],
    'گل محمدی': [r'گل\s*محمدی'],
    'بهارنارنج': [r'بهار\s*نارنج'],
    'تلخ': [r'تلخ'],
    'شیرین': [r'شیرین'],
}

FOOD_FORM_PATTERNS = {
    'سرلاشه': [r'سر\s*لاشه', r'سرلاشه'],
    'نیم دانه': [r'نیم\s*دانه', r'نیمدانه'],
    'پودر': [r'پودر'],
    'دانه': [r'دانه'],
    'پرک': [r'پرک'],
}

ACCESSORY_PATTERNS = {
    'accessory': [r'قاب', r'گلس', r'کاور', r'محافظ', r'یدکی', r'قطعه', r'فیلتر', r'کابل'],
    'main': [r'گوشی\s*موبایل', r'موبایل', r'دستگاه', r'کنسول'],
}

TECHNICAL_FAMILIES = {'digital', 'home_appliance', 'tools', 'tools_auto', 'auto_part', 'generic'}
QUANTITY_SENSITIVE_FAMILIES = {'digital', 'home_appliance', 'tools', 'tools_auto', 'auto_part', 'home_living', 'generic'}
FOOD_FAMILIES = {'food'}
IDENTITY_POLICY_VERSION = 'identity_policy_v1'


@dataclass
class ProductIdentity:
    title: str = ''
    family: str = 'generic'
    product_type: str = ''
    core_tokens: list[str] = field(default_factory=list)
    strong_anchors: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    model_tokens: list[str] = field(default_factory=list)
    person_counts: list[int] = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    package_counts: list[int] = field(default_factory=list)
    capacity_values: list[dict] = field(default_factory=list)
    food_ingredients: list[str] = field(default_factory=list)
    food_varieties: list[str] = field(default_factory=list)
    food_forms: list[str] = field(default_factory=list)
    product_roles: list[str] = field(default_factory=list)
    measurement: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            'title': self.title,
            'family': self.family,
            'product_type': self.product_type,
            'core_tokens': self.core_tokens,
            'strong_anchors': self.strong_anchors,
            'brands': self.brands,
            'model_tokens': self.model_tokens,
            'person_counts': self.person_counts,
            'dimensions': self.dimensions,
            'package_counts': self.package_counts,
            'capacity_values': self.capacity_values,
            'food_ingredients': self.food_ingredients,
            'food_varieties': self.food_varieties,
            'food_forms': self.food_forms,
            'product_roles': self.product_roles,
            'measurement': self.measurement,
        }


@dataclass
class MatchPolicyResult:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    identity_score: float = 0
    policy: str = IDENTITY_POLICY_VERSION

    @property
    def accepted(self):
        return not self.blockers

    def to_dict(self):
        return {
            'accepted': self.accepted,
            'blockers': self.blockers,
            'warnings': self.warnings,
            'evidence': self.evidence,
            'identity_score': self.identity_score,
            'policy': self.policy,
        }


@dataclass(frozen=True)
class QuerySpec:
    query: str
    kind: str
    priority: int
    required_terms: tuple[str, ...] = ()

    def to_dict(self):
        return {
            'query': self.query,
            'kind': self.kind,
            'priority': self.priority,
            'required_terms': list(self.required_terms),
        }


def compact_spaces(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def strip_noise(value):
    text = normalize_text(value)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, ' ', text)
    text = re.sub(r'[^\w\s؀-ۿx\-]+', ' ', text, flags=re.UNICODE)
    return compact_spaces(text)


def token_list(value):
    return [token for token in normalize_for_tokens(strip_noise(value)).split() if len(token) > 1 and token not in STOP_TOKENS]


def alias_hits(text, mapping):
    found = set()
    normalized = normalize_text(text)
    for key, patterns in mapping.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            found.add(key)
    return found


def first_product_type(title):
    hits = alias_hits(title, PRODUCT_TYPE_PATTERNS)
    if not hits:
        tokens = token_list(title)
        return tokens[0] if tokens else ''
    return sorted(hits, key=lambda item: (-len(item), item))[0]


def extract_person_counts(text):
    normalized = normalize_text(text)
    return {int(match.group(1)) for match in re.finditer(r'(\d+)\s*نفره', normalized)}


def extract_piece_counts(text):
    normalized = normalize_text(text)
    values = set()
    for match in re.finditer(r'(\d+)\s*(?:پارچه|کشو|عددی|تایی|عدد)\b', normalized):
        value = int(match.group(1))
        if 1 < value <= 500:
            values.add(value)
    return values


def normalize_capacity(value, unit):
    unit = normalize_text(unit)
    amount = float(str(value).replace('/', '.'))
    if unit in {'ترابایت', 'tb'}:
        return {'value': int(amount * 1024), 'unit': 'gb'}
    if unit in {'گیگ', 'گیگابایت', 'gb'}:
        return {'value': int(amount), 'unit': 'gb'}
    if unit in {'لیتر', 'لیتری'}:
        return {'value': round(amount * 1000, 3), 'unit': 'ml'}
    if unit in {'میل', 'میلی لیتر'}:
        return {'value': round(amount, 3), 'unit': 'ml'}
    if unit in {'کیلو', 'کیلوگرم', 'کیلو گرم', 'کیلویی', 'کیلوگرمی'}:
        return {'value': round(amount * 1000, 3), 'unit': 'g'}
    if unit in {'گرم', 'گرمی'}:
        return {'value': round(amount, 3), 'unit': 'g'}
    return {'value': amount, 'unit': unit}


def extract_capacity_values(text):
    normalized = normalize_text(text)
    values = []
    unit_pattern = r'ترابایت|tb|گیگابایت|گیگ|gb|لیتری|لیتر|میلی\s*لیتر|میل|کیلوگرم|کیلو\s*گرم|کیلوگرمی|کیلویی|کیلو|گرمی|گرم'
    for match in re.finditer(rf'(\d+(?:[./]\d+)?)\s*({unit_pattern})', normalized):
        unit = match.group(2).replace('میلی لیتر', 'میلی لیتر')
        values.append(normalize_capacity(match.group(1), unit))
    return values


def extract_product_roles(text):
    normalized = normalize_text(text)
    roles = set()
    for role, patterns in ACCESSORY_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            roles.add(role)
    return roles


def normalize_model_tokens(tokens):
    normalized = set()
    for token in tokens or []:
        value = re.sub(r'[^a-z0-9]', '', str(token).lower())
        if not value or value in {'1404', '1405', '2025', '2026'}:
            continue
        if re.fullmatch(r'\d+', value) and len(value) < 4:
            continue
        normalized.add(value)
    return normalized


def measurement_dict(measurement):
    return {
        'canonical_unit': measurement.canonical_unit,
        'group': measurement.group,
        'normalized_quantity': measurement.normalized_quantity,
        'basis': measurement.basis,
        'confidence': measurement.confidence,
        'title_unit': measurement.title_unit,
        'title_normalized_quantity': measurement.title_normalized_quantity,
    }


def extract_product_identity(*, title='', text='', category_title='', category_parent_title='', navigation_slug='', unit_type='', unit_quantity=0, net_weight=0):
    route = route_product_family(
        category_title=category_title,
        navigation_title='',
        navigation_slug=navigation_slug,
        title=title,
        attributes_text=text,
    )
    family = route.get('family') or 'generic'
    full_text = ' | '.join([title or '', text or '', category_title or '', category_parent_title or ''])
    cues = extract_cues(title, full_text, families={family})
    measurement = normalize_measurement(unit_type=unit_type, unit_quantity=unit_quantity, net_weight=net_weight, title=title)

    food_ingredients = alias_hits(full_text, FOOD_INGREDIENT_PATTERNS)
    food_varieties = alias_hits(full_text, FOOD_VARIETY_PATTERNS)
    food_forms = alias_hits(full_text, FOOD_FORM_PATTERNS)
    model_tokens = normalize_model_tokens(cues.get('model_tokens'))
    product_type = first_product_type(title or category_title)
    core_tokens = token_list(' '.join([title or '', category_title or '']))
    person_counts = extract_person_counts(title)
    package_counts = set(cues.get('package_counts') or []) | extract_piece_counts(title)
    capacity_values = extract_capacity_values(title)
    roles = set(cues.get('product_roles') or []) | extract_product_roles(title)

    strong_anchors = set()
    strong_anchors.update(cues.get('brands') or [])
    strong_anchors.update(model_tokens)
    strong_anchors.update(food_ingredients)
    strong_anchors.update(food_varieties)
    strong_anchors.update(food_forms)
    strong_anchors.update(str(value) for value in person_counts)
    strong_anchors.update(f"{row['value']}:{row['unit']}" for row in capacity_values)
    if product_type:
        strong_anchors.add(product_type)

    return ProductIdentity(
        title=compact_spaces(title),
        family=family,
        product_type=product_type,
        core_tokens=sorted(set(core_tokens)),
        strong_anchors=sorted(strong_anchors, key=str),
        brands=sorted(cues.get('brands') or []),
        model_tokens=sorted(model_tokens),
        person_counts=sorted(person_counts),
        dimensions=cues.get('dimensions') or [],
        package_counts=sorted(package_counts),
        capacity_values=capacity_values,
        food_ingredients=sorted(food_ingredients),
        food_varieties=sorted(food_varieties),
        food_forms=sorted(food_forms),
        product_roles=sorted(roles),
        measurement=measurement_dict(measurement),
    )


def extract_snapshot_identity(snapshot):
    return extract_product_identity(
        title=getattr(snapshot, 'title', ''),
        text=' | '.join([
            str(getattr(snapshot, 'attributes_text', '') or ''),
            str(getattr(snapshot, 'description', '') or ''),
            str(getattr(snapshot, 'summary', '') or ''),
        ]),
        category_title=getattr(snapshot, 'category_title', ''),
        category_parent_title=getattr(snapshot, 'category_parent_title', ''),
        navigation_slug=getattr(snapshot, 'navigation_slug', ''),
        unit_type=getattr(snapshot, 'unit_type', ''),
        unit_quantity=getattr(snapshot, 'unit_quantity', 0),
        net_weight=getattr(snapshot, 'net_weight', 0),
    )


def extract_candidate_identity(candidate):
    return extract_product_identity(
        title=candidate.get('candidate_title', ''),
        text=' | '.join([
            str(candidate.get('candidate_attributes_text') or ''),
            str(candidate.get('candidate_description') or ''),
            str(candidate.get('candidate_summary') or ''),
        ]),
        category_title=candidate.get('candidate_category_title', ''),
        category_parent_title=candidate.get('candidate_category_parent_title', ''),
        navigation_slug=candidate.get('candidate_navigation_slug', ''),
        unit_type=candidate.get('candidate_unit_type', ''),
        unit_quantity=candidate.get('candidate_unit_quantity', 0),
        net_weight=candidate.get('candidate_net_weight', 0),
    )


def add_blocker(result, reason, source_values, candidate_values, *, key, details=None):
    if reason not in result.blockers:
        result.blockers.append(reason)
    result.evidence.append({
        'rule': reason,
        'reason_code': reason,
        'severity': 'blocker',
        'confidence': 'high',
        'key': key,
        'source': {'values': sorted(source_values, key=str)},
        'candidate': {'values': sorted(candidate_values, key=str)},
        'details': details or {},
    })


def has_disjoint(left, right):
    left = set(left or [])
    right = set(right or [])
    return left and right and left.isdisjoint(right)


def families_allow_model_blocker(source, candidate):
    families = {source.family, candidate.family} - {''}
    return not families or bool(families & TECHNICAL_FAMILIES)


def capacity_signature(rows):
    return {f"{row.get('value')}:{row.get('unit')}" for row in rows or [] if row.get('value') and row.get('unit')}


def model_code_set(identity):
    return {token for token in identity.model_tokens or [] if any(char.isdigit() for char in token)}


def comparable_capacity_mismatch(source, candidate):
    source_rows = source.capacity_values or []
    candidate_rows = candidate.capacity_values or []
    pairs = []
    for source_row in source_rows:
        for candidate_row in candidate_rows:
            if source_row.get('unit') == candidate_row.get('unit'):
                pairs.append((source_row, candidate_row))
    if not pairs:
        return False
    for source_row, candidate_row in pairs:
        source_value = float(source_row.get('value') or 0)
        candidate_value = float(candidate_row.get('value') or 0)
        if source_value and candidate_value and abs(source_value - candidate_value) / max(source_value, candidate_value) <= 0.05:
            return False
    return True


def core_overlap_score(source, candidate):
    source_tokens = set(source.core_tokens or [])
    candidate_tokens = set(candidate.core_tokens or [])
    if not source_tokens or not candidate_tokens:
        return 0
    return len(source_tokens & candidate_tokens) / max(len(source_tokens | candidate_tokens), 1)


def shared_strong_anchors(source, candidate):
    ignored = {source.product_type, candidate.product_type, ''}
    return (set(source.strong_anchors or []) & set(candidate.strong_anchors or [])) - ignored


def compare_product_identities(source, candidate):
    result = MatchPolicyResult()

    if has_disjoint(source.person_counts, candidate.person_counts):
        add_blocker(result, 'identity_person_capacity_mismatch', source.person_counts, candidate.person_counts, key='person_counts')

    source_model_codes = model_code_set(source)
    candidate_model_codes = model_code_set(candidate)
    if families_allow_model_blocker(source, candidate) and has_disjoint(source_model_codes, candidate_model_codes):
        add_blocker(result, 'identity_model_mismatch', source_model_codes, candidate_model_codes, key='model_tokens')

    if {source.family, candidate.family} & QUANTITY_SENSITIVE_FAMILIES and comparable_capacity_mismatch(source, candidate):
        add_blocker(result, 'identity_measurement_mismatch', capacity_signature(source.capacity_values), capacity_signature(candidate.capacity_values), key='capacity_values')

    source_family_set = {source.family, candidate.family}
    food_context = bool(source_family_set & FOOD_FAMILIES) or source.product_type in {'برنج', 'فلفل', 'آرد', 'کره', 'روغن', 'ماهی', 'عسل', 'گوشت', 'حبوبات', 'شربت'} or candidate.product_type in {'برنج', 'فلفل', 'آرد', 'کره', 'روغن', 'ماهی', 'عسل', 'گوشت', 'حبوبات', 'شربت'}
    if food_context:
        if has_disjoint(source.food_ingredients, candidate.food_ingredients):
            add_blocker(result, 'identity_food_base_mismatch', source.food_ingredients, candidate.food_ingredients, key='food_ingredients')
        if has_disjoint(source.food_varieties, candidate.food_varieties):
            add_blocker(result, 'identity_food_variety_mismatch', source.food_varieties, candidate.food_varieties, key='food_varieties')
        if has_disjoint(source.food_forms, candidate.food_forms):
            add_blocker(result, 'identity_food_form_mismatch', source.food_forms, candidate.food_forms, key='food_forms')

    if source.product_roles and candidate.product_roles and has_disjoint(source.product_roles, candidate.product_roles):
        add_blocker(result, 'identity_role_mismatch', source.product_roles, candidate.product_roles, key='product_roles')

    overlap = core_overlap_score(source, candidate)
    result.identity_score = round(overlap, 4)
    if overlap < 0.16 and not shared_strong_anchors(source, candidate):
        add_blocker(
            result,
            'identity_low_anchor_overlap',
            source.core_tokens[:12],
            candidate.core_tokens[:12],
            key='core_tokens',
            details={'core_overlap_score': result.identity_score},
        )
    elif overlap < 0.28 and not shared_strong_anchors(source, candidate):
        result.warnings.append('identity_weak_anchor_overlap')

    return result


def query_text(value):
    return compact_spaces(strip_noise(value))


def unique_query_specs(specs, max_queries):
    unique = []
    seen = set()
    for spec in sorted(specs, key=lambda item: item.priority):
        query = query_text(spec.query)
        if len(query) < 3:
            continue
        key = normalize_for_tokens(query)
        if key in seen:
            continue
        seen.add(key)
        unique.append(QuerySpec(query=query, kind=spec.kind, priority=spec.priority, required_terms=spec.required_terms))
        if len(unique) >= max_queries:
            break
    return unique


def plan_search_queries(snapshot, *, max_queries=4):
    identity = extract_snapshot_identity(snapshot)
    specs = [QuerySpec(query=getattr(snapshot, 'title', '') or '', kind='full_title', priority=10)]
    core = ' '.join(identity.core_tokens[:10])
    if core:
        specs.append(QuerySpec(query=core, kind='core_title', priority=20))

    anchor_parts = []
    if identity.brands:
        anchor_parts.extend(identity.brands[:1])
    if identity.model_tokens:
        anchor_parts.extend(identity.model_tokens[:2])
    if identity.food_ingredients:
        anchor_parts.extend(identity.food_ingredients[:2])
    if identity.food_varieties:
        anchor_parts.extend(identity.food_varieties[:2])
    if identity.food_forms:
        anchor_parts.extend(identity.food_forms[:1])
    if identity.product_type and identity.product_type not in anchor_parts:
        anchor_parts.insert(0, identity.product_type)
    if identity.person_counts:
        anchor_parts.append(f'{identity.person_counts[0]} نفره')
    if identity.capacity_values:
        row = identity.capacity_values[0]
        anchor_parts.append(f"{row.get('value')} {row.get('unit')}")
    if len(anchor_parts) >= 2:
        specs.append(QuerySpec(query=' '.join(str(part) for part in anchor_parts if part), kind='identity_anchor', priority=5, required_terms=tuple(str(part) for part in anchor_parts[:3])))

    if identity.product_type and identity.strong_anchors:
        fallback_parts = [identity.product_type, *[item for item in identity.strong_anchors if item != identity.product_type][:3]]
        specs.append(QuerySpec(query=' '.join(fallback_parts), kind='category_anchor', priority=30, required_terms=tuple(fallback_parts[:2])))

    return unique_query_specs(specs, max_queries=max(1, max_queries))
