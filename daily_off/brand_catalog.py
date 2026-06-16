import json
import re
from functools import lru_cache
from pathlib import Path


PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'brand_catalog.json'


MANUAL_ALIASES = {
    'LG': ['ال جی', 'الجی', 'ال‌جی', 'lg'],
    'GPlus': ['جی پلاس', 'جی‌پلاس', 'g plus', 'gplus'],
    'OnePlus': ['وان پلاس', 'وان‌پلاس', 'one plus', 'oneplus'],
    'GE Appliances': ['جنرال الکتریک', 'general electric', 'ge appliances'],
    'KitchenAid': ['کیتچن اید', 'کیتچن‌اید', 'kitchen aid', 'kitchenaid'],
    'Maytag': ['می تگ', 'می‌تگ', 'may tag', 'maytag'],
}


@lru_cache(maxsize=1)
def load_brand_catalog():
    if not CATALOG_PATH.exists():
        return []
    rows = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    enriched = []
    for row in rows:
        aliases = set(row.get('aliases') or [])
        aliases.add(row.get('canonical_name') or '')
        aliases.add(row.get('english_name') or '')
        aliases.add(row.get('persian_name') or '')
        for alias in MANUAL_ALIASES.get(row.get('canonical_name'), []):
            aliases.add(alias)
        enriched.append({**row, 'aliases': sorted(alias for alias in aliases if alias)})
    return enriched


@lru_cache(maxsize=1)
def brand_alias_index():
    index = {}
    for row in load_brand_catalog():
        for alias in row.get('aliases') or []:
            normalized = normalize_brand_alias(alias)
            if normalized:
                index.setdefault(normalized, []).append(row)
    return index


def normalize_brand_alias(value):
    text = str(value or '').translate(PERSIAN_DIGITS)
    text = text.replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s؀-ۿ]+', ' ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def alias_pattern(alias):
    normalized = normalize_brand_alias(alias)
    if not normalized:
        return None
    parts = [re.escape(part) for part in normalized.split()]
    separator = r'[\s\-_‌]*'
    body = separator.join(parts)
    if re.search(r'[a-z0-9]', normalized):
        return re.compile(rf'(?<![a-z0-9]){body}(?![a-z0-9])', re.IGNORECASE)
    return re.compile(rf'(?<!\w){body}(?!\w)', re.IGNORECASE)


@lru_cache(maxsize=1)
def compiled_brand_patterns():
    patterns = []
    for row in load_brand_catalog():
        for alias in row.get('aliases') or []:
            pattern = alias_pattern(alias)
            if pattern:
                patterns.append((pattern, row))
    patterns.sort(key=lambda item: len(item[0].pattern), reverse=True)
    return patterns


def family_matches(row_family, families):
    if not families:
        return True
    if 'generic' in families:
        return True
    return row_family in families


def detect_brands(text, families=None):
    normalized_text = normalize_brand_alias(text)
    families = set(families or []) - {''}
    found = {}
    for pattern, row in compiled_brand_patterns():
        if not family_matches(row.get('family'), families):
            continue
        if pattern.search(normalized_text):
            canonical = row.get('canonical_name') or row.get('english_name') or row.get('persian_name')
            found[canonical] = {
                'canonical_name': canonical,
                'family': row.get('family'),
                'english_name': row.get('english_name') or '',
                'persian_name': row.get('persian_name') or '',
            }
    return found
