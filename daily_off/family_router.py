from .category_catalog import resolve_category_path
from .semantic_rules import normalize_text


LEVEL1_TO_FAMILY = {
    'کالای دیجیتال': 'digital',
    'مواد غذایی': 'food',
    'مد و پوشاک': 'fashion',
    'آرایشی و بهداشتی': 'beauty_health',
    'فرهنگی، آموزشی و سرگرمی': 'culture_entertainment',
    'ورزش و سفر': 'sport_travel',
    'سلامت، درمان و طب': 'health_medical',
    'صنایع دستی': 'handicraft',
    'طلا و نقره': 'jewelry',
    'خانه و آشپزخانه': 'home_living',
    'ابزارآلات و تجهیزات خودرو': 'tools_auto',
}

LEVEL2_TO_FAMILY = {
    'لوازم یدکی خودرو': 'auto_part',
    'لوازم جانبی خودرو': 'auto_part',
    'ابزار برقی': 'tools',
    'ابزار دستی': 'tools',
    'لوازم برقی': 'home_appliance',
    'گوشی موبایل': 'digital',
}

TITLE_CUES = [
    ('home_appliance', ['کولر', 'یخچال', 'لباسشویی', 'جاروبرقی', 'اجاق', 'مایکروویو']),
    ('tools', ['دریل', 'فرز', 'پیچ گوشتی', 'آچار', 'اره', 'کمپرسور']),
    ('auto_part', ['لنت', 'کمک فنر', 'شمع خودرو', 'روغن موتور', 'فیلتر هوا']),
    ('digital', ['گوشی', 'موبایل', 'لپ تاپ', 'تبلت', 'هندزفری', 'شارژر']),
    ('food', ['عسل', 'برنج', 'زعفران', 'چای', 'آجیل', 'بادام', 'خرما']),
]

GENERIC_TITLES = {'سایر', 'متفرقه'}


def category_is_generic(category_path):
    titles = [category_path.get('leaf') or '', category_path.get('lvl2') or '', category_path.get('lvl3') or '']
    normalized = [normalize_text(title) for title in titles if normalize_text(title)]
    if not normalized:
        return True
    return bool(set(normalized) & {normalize_text(title) for title in GENERIC_TITLES})


def title_family_cue(title='', attributes_text=''):
    text = normalize_text(' | '.join([title or '', attributes_text or '']))
    for family, cues in TITLE_CUES:
        if any(normalize_text(cue) in text for cue in cues):
            return family
    return ''


def route_family(category_path=None, title='', attributes_text=''):
    category_path = category_path or resolve_category_path()
    signals = []
    family = ''
    confidence = 'low'

    lvl2 = category_path.get('lvl2') or ''
    lvl1 = category_path.get('lvl1') or ''
    if lvl2 in LEVEL2_TO_FAMILY:
        family = LEVEL2_TO_FAMILY[lvl2]
        confidence = 'high'
        signals.append('level2_override')
    elif lvl1 in LEVEL1_TO_FAMILY:
        family = LEVEL1_TO_FAMILY[lvl1]
        confidence = 'high' if category_path.get('confidence') == 'high' else 'medium'
        signals.append('level1')

    cue_family = title_family_cue(title, attributes_text)
    if not family or category_is_generic(category_path):
        if cue_family:
            family = cue_family
            confidence = 'medium' if family else 'low'
            signals.append('title_cue')

    if not family:
        family = 'generic'
        confidence = 'low'
        signals.append('fallback_generic')

    return {
        'family': family,
        'confidence': confidence,
        'signals': signals,
        'category_path': category_path,
    }


def route_product_family(category_title='', navigation_title='', navigation_slug='', title='', attributes_text=''):
    category_path = resolve_category_path(
        category_title=category_title,
        navigation_title=navigation_title,
        navigation_slug=navigation_slug,
    )
    return route_family(category_path, title=title, attributes_text=attributes_text)
