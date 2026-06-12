import re
from dataclasses import dataclass, field


PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


@dataclass
class SemanticComparison:
    blocker_reasons: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)


def normalize_text(value):
    text = str(value or '').translate(PERSIAN_DIGITS)
    text = text.replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    text = text.replace('×', 'x').replace('*', 'x')
    text = re.sub(r'[‎‏\x00-\x1f\x7f]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def normalize_for_tokens(value):
    text = normalize_text(value)
    text = re.sub(r'[^\w\s؀-ۿx]+', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def has_any(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)


def alias_hits(text, aliases):
    found = set()
    for key, patterns in aliases.items():
        if has_any(text, patterns):
            found.add(key)
    return found


HONEY_TYPES = {
    'گون': [r'\bگون\b', r'گون\s*گز'],
    'چهل_گیاه': [r'چهل\s*گیاه', r'40\s*گیاه'],
    'چند_گیاه': [r'چند\s*گیاه'],
    'تابستانه': [r'تابستانه'],
}

HONEY_CLAIMS = {
    'دیابتی': [r'دیابتی', r'مناسب\s*دیابت', r'درمانی'],
    'ساکاروز': [r'ساکاروز'],
}

FISH_TYPES = {
    'هوور': [r'\bهوور\b'],
    'حسون': [r'\bحسون\b'],
    'طلال': [r'\bطلال\b'],
    'کوتر': [r'\bکوتر\b', r'باراکودا', r'چنگو'],
}

BRAND_ALIASES = {
    'باس': [r'\bباس\b', r'\bboss\b'],
    'ماکیتا': [r'ماکیتا', r'\bmakita\b'],
    'اینتیمکث': [r'اینتیمکث', r'اینتمکس', r'اینتیمکس', r'\bintim(?:a|e)?x\b'],
    'هایسنس': [r'هایسنس', r'\bhisense\b'],
    'جنرال_مکس': [r'جنرال\s*مکس', r'\bgeneral\s*max\b', r'\bgeneralmax\b'],
}

NUT_MIX_TYPES = {
    'چهارمغز': [r'چهار\s*مغز', r'4\s*مغز'],
    'پنج_مغز': [r'پنج\s*مغز', r'5\s*مغز'],
    'سلامت': [r'آجیل\s*سلامت'],
}

MATERIAL_QUALITY = {
    'ضدزنگ': [r'ضد\s*زنگ', r'استیل', r'زنگ\s*نزن'],
    'فولادی': [r'فولاد', r'فولادی'],
    'پلاستیکی': [r'پلاستیک', r'پلاستیکی'],
    'چوبی': [r'چوبی', r'چوب'],
}


def extract_dimensions(text):
    dims = set()
    normalized = normalize_text(text)
    pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(?:x|در|به)\s*(\d+(?:\.\d+)?)(?:\s*(?:x|در|به)\s*(\d+(?:\.\d+)?))?')
    for match in pattern.finditer(normalized):
        numbers = [float(item) for item in match.groups() if item]
        if len(numbers) >= 2:
            dims.add(tuple(sorted(numbers)))
    return dims


def extract_wattages(text):
    normalized = normalize_text(text)
    return {int(match.group(1)) for match in re.finditer(r'(\d{3,5})\s*(?:وات|w\b)', normalized)}


def extract_capacities(text):
    normalized = normalize_text(text)
    if not re.search(r'کولر|گازی|اسپلیت', normalized):
        return set()
    capacities = set()
    for match in re.finditer(r'\b(\d{2})\s*هزار\b', normalized):
        capacities.add(int(match.group(1)) * 1000)
    for match in re.finditer(r'\b(1[2-9]000|2[0-9]000|3[0-6]000)\b', normalized):
        capacities.add(int(match.group(1)))
    return capacities


def extract_model_tokens(text):
    normalized = normalize_for_tokens(text)
    tokens = set()
    for match in re.finditer(r'مدل\s*([a-z0-9\-]{2,})', normalized):
        token = match.group(1).strip('-')
        if token:
            tokens.add(token)
    for token in normalized.split():
        if re.search(r'[a-z]', token) and re.search(r'\d', token) and len(token) >= 3:
            tokens.add(token)
    return tokens


def extract_package_counts(text):
    normalized = normalize_text(text)
    counts = set()
    for match in re.finditer(r'(?:بسته|پک)?\s*(\d+)\s*(?:عددی|تایی|عدد|بسته)\b', normalized):
        count = int(match.group(1))
        if 1 < count <= 200:
            counts.add(count)
    return counts


def extract_compartment_counts(text):
    normalized = normalize_text(text)
    return {int(match.group(1)) for match in re.finditer(r'(\d+)\s*خانه\b', normalized)}


def extract_sucrose_values(text):
    normalized = normalize_text(text)
    values = set()
    for match in re.finditer(r'ساکاروز\s*(\d+(?:\.\d+)?)\s*(?:درصد|%)?', normalized):
        values.add(float(match.group(1)))
    return values


def detect_wholesale(text):
    normalized = normalize_text(text)
    return bool(re.search(r'عمده|عمده\s*فروشی|کارتنی', normalized))


def detect_product_roles(text):
    normalized = normalize_text(text)
    roles = set()
    game_context = re.search(r'کنسول|game\s*stick|پلی\s*استیشن|ایکس\s*باکس|ps[45]?|xbox', normalized)
    if game_context:
        if re.search(r'دسته|یدکی|لوازم\s*جانبی', normalized):
            roles.add('game_accessory')
        if re.search(r'کنسول|game\s*stick|دستگاه', normalized) and 'game_accessory' not in roles:
            roles.add('game_console')
    return roles


def extract_cues(title, text=''):
    title_norm = normalize_text(title)
    full_text = normalize_text(' | '.join([title or '', text or '']))
    title_token_text = normalize_for_tokens(title)
    full_token_text = normalize_for_tokens(' | '.join([title or '', text or '']))
    return {
        'is_honey': 'عسل' in full_text,
        'honey_types': sorted(alias_hits(full_text, HONEY_TYPES)),
        'honey_claims': sorted(alias_hits(full_text, HONEY_CLAIMS)),
        'honey_sucrose_values': sorted(extract_sucrose_values(full_text)),
        'fish_types': sorted(alias_hits(full_text, FISH_TYPES)),
        'brands': sorted(alias_hits(full_token_text, BRAND_ALIASES)),
        'dimensions': sorted(extract_dimensions(title_norm)),
        'capacities': sorted(extract_capacities(title_norm)),
        'wattages': sorted(extract_wattages(title_norm)),
        'model_tokens': sorted(extract_model_tokens(title_token_text)),
        'package_counts': sorted(extract_package_counts(title_norm)),
        'compartment_counts': sorted(extract_compartment_counts(title_norm)),
        'wholesale': detect_wholesale(title_norm),
        'product_roles': sorted(detect_product_roles(title_norm)),
        'nut_mixes': sorted(alias_hits(full_text, NUT_MIX_TYPES)),
        'materials': sorted(alias_hits(full_text, MATERIAL_QUALITY)),
    }


def set_from(cues, key):
    return set(cues.get(key) or [])


def sorted_values(values):
    return sorted(values, key=lambda item: str(item))


def add_evidence(evidence, reason, source_values, candidate_values, *, key='', details=None):
    evidence.append({
        'rule': reason,
        'reason_code': reason,
        'severity': 'blocker',
        'confidence': 'high',
        'key': key,
        'source': {'values': sorted_values(source_values)},
        'candidate': {'values': sorted_values(candidate_values)},
        'details': details or {},
    })


def add_if_disjoint(reasons, evidence, reason, source_values, candidate_values, *, key=''):
    if source_values and candidate_values and source_values.isdisjoint(candidate_values):
        reasons.append(reason)
        add_evidence(evidence, reason, source_values, candidate_values, key=key)


TECHNICAL_STRICT_FAMILIES = {'tools', 'digital', 'home_appliance', 'tools_auto', 'auto_part'}


def family_allows_strict_rule(source_family='', candidate_family=''):
    families = {source_family or '', candidate_family or ''} - {''}
    if not families:
        return True
    if families & {'generic'}:
        return True
    return bool(families & TECHNICAL_STRICT_FAMILIES)


def compare_semantic_cues(
    *,
    source_title='',
    source_text='',
    candidate_title='',
    candidate_text='',
    source_family='',
    candidate_family='',
):
    source = extract_cues(source_title, source_text)
    candidate = extract_cues(candidate_title, candidate_text)
    reasons = []
    evidence = []

    add_if_disjoint(
        reasons,
        evidence,
        'semantic_honey_subtype_mismatch',
        set_from(source, 'honey_types'),
        set_from(candidate, 'honey_types'),
        key='honey_types',
    )
    if source.get('is_honey'):
        source_claims = set_from(source, 'honey_claims')
        candidate_claims = set_from(candidate, 'honey_claims')
        missing_claims = source_claims - candidate_claims
        if missing_claims:
            reasons.append('semantic_honey_claim_missing')
            add_evidence(
                evidence,
                'semantic_honey_claim_missing',
                source_claims,
                candidate_claims,
                key='honey_claims',
                details={'missing_claims': sorted_values(missing_claims)},
            )
        source_sucrose = set_from(source, 'honey_sucrose_values')
        candidate_sucrose = set_from(candidate, 'honey_sucrose_values')
        if source_sucrose and (not candidate_sucrose or source_sucrose.isdisjoint(candidate_sucrose)):
            if 'semantic_honey_claim_missing' not in reasons:
                reasons.append('semantic_honey_claim_missing')
                add_evidence(
                    evidence,
                    'semantic_honey_claim_missing',
                    source_sucrose,
                    candidate_sucrose,
                    key='honey_sucrose_values',
                    details={'missing_or_different_sucrose': True},
                )

    semantic_keys = [
        ('semantic_fish_type_mismatch', 'fish_types'),
        ('semantic_dimension_mismatch', 'dimensions'),
        ('semantic_capacity_mismatch', 'capacities'),
        ('semantic_package_count_mismatch', 'package_counts'),
        ('semantic_compartment_count_mismatch', 'compartment_counts'),
        ('semantic_nut_mix_mismatch', 'nut_mixes'),
    ]
    if family_allows_strict_rule(source_family, candidate_family):
        semantic_keys.extend([
            ('semantic_brand_mismatch', 'brands'),
            ('semantic_wattage_mismatch', 'wattages'),
            ('semantic_model_mismatch', 'model_tokens'),
        ])
    for reason, key in semantic_keys:
        add_if_disjoint(reasons, evidence, reason, set_from(source, key), set_from(candidate, key), key=key)

    if source.get('wholesale') != candidate.get('wholesale') and (source.get('wholesale') or candidate.get('wholesale')):
        reasons.append('semantic_wholesale_mismatch')
        add_evidence(
            evidence,
            'semantic_wholesale_mismatch',
            {source.get('wholesale')},
            {candidate.get('wholesale')},
            key='wholesale',
        )

    source_roles = set_from(source, 'product_roles')
    candidate_roles = set_from(candidate, 'product_roles')
    if source_roles and candidate_roles and source_roles.isdisjoint(candidate_roles):
        reasons.append('semantic_accessory_main_mismatch')
        add_evidence(evidence, 'semantic_accessory_main_mismatch', source_roles, candidate_roles, key='product_roles')

    add_if_disjoint(
        reasons,
        evidence,
        'semantic_material_mismatch',
        set_from(source, 'materials'),
        set_from(candidate, 'materials'),
        key='materials',
    )

    blocker_reasons = sorted(set(reasons), key=reasons.index)
    return SemanticComparison(
        blocker_reasons=blocker_reasons,
        details={
            'source': source,
            'candidate': candidate,
            'evidence': [row for row in evidence if row.get('reason_code') in blocker_reasons],
        },
        evidence=[row for row in evidence if row.get('reason_code') in blocker_reasons],
    )
