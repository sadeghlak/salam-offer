import json
import re
from functools import lru_cache
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'category_catalog.json'


def normalize_category_title(value):
    text = str(value or '')
    text = re.sub(r'[أإآ]', 'ا', text)
    text = text.replace('ي', 'ی').replace('ك', 'ک')
    text = re.sub(r'[‌‏\x00-\x1f\x7f]+', ' ', text)
    text = re.sub(r'[^\w\s؀-ۿ]+', ' ', text, flags=re.UNICODE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


@lru_cache(maxsize=1)
def load_category_catalog():
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def category_catalog_index():
    index = {}
    for row in load_category_catalog():
        titles = [
            row.get('cat_leaf_title'),
            row.get('cat_lvl3_title'),
            row.get('cat_lvl2_title'),
        ]
        for title in titles:
            normalized = normalize_category_title(title)
            if normalized and normalized not in index:
                index[normalized] = row
    return index


def category_path_from_row(row, *, matched_title='', matched_level='', confidence='high'):
    if not row:
        return {
            'leaf': '',
            'lvl3': '',
            'lvl2': '',
            'lvl1': '',
            'matched_title': matched_title,
            'matched_level': matched_level,
            'confidence': 'low',
        }
    return {
        'leaf': row.get('cat_leaf_title') or '',
        'lvl3': row.get('cat_lvl3_title') or '',
        'lvl2': row.get('cat_lvl2_title') or '',
        'lvl1': row.get('cat_lvl1_title') or '',
        'cat_lvl1_id': row.get('cat_lvl1_id'),
        'cat_lvl2_id': row.get('cat_lvl2_id'),
        'cat_lvl3_id': row.get('cat_lvl3_id'),
        'matched_title': matched_title,
        'matched_level': matched_level,
        'confidence': confidence,
    }


def resolve_category_path(category_title='', navigation_title='', navigation_slug=''):
    index = category_catalog_index()
    candidates = [
        ('leaf_or_level', category_title),
        ('navigation_title', navigation_title),
    ]
    for matched_level, title in candidates:
        normalized = normalize_category_title(title)
        if normalized and normalized in index:
            return category_path_from_row(
                index[normalized],
                matched_title=title,
                matched_level=matched_level,
                confidence='high',
            )

    return category_path_from_row(
        None,
        matched_title=category_title or navigation_title or navigation_slug or '',
        matched_level='unknown',
        confidence='low',
    )
