from types import SimpleNamespace

from django.test import SimpleTestCase

from .analysis_engine import AnalysisConfig, score_candidate
from .models import DailyProductSnapshot
from .semantic_rules import compare_semantic_cues


class SemanticRulesTests(SimpleTestCase):
    def assertBlocked(self, source, candidate, reason):
        comparison = compare_semantic_cues(source_title=source, source_text=source, candidate_title=candidate, candidate_text=candidate)
        self.assertIn(reason, comparison.blocker_reasons)

    def assertNotBlocked(self, source, candidate, reason):
        comparison = compare_semantic_cues(source_title=source, source_text=source, candidate_title=candidate, candidate_text=candidate)
        self.assertNotIn(reason, comparison.blocker_reasons)

    def test_honey_subtype_mismatch_and_forty_plant_equivalence(self):
        self.assertBlocked(
            'عسل تابستانه چند گیاه کوهی 1000 گرم',
            'عسل طبیعی چهل گیاه خوش طعم',
            'semantic_honey_subtype_mismatch',
        )
        self.assertNotBlocked(
            'عسل طبیعی چهل گیاه',
            'عسل طبیعی 40 گیاه',
            'semantic_honey_subtype_mismatch',
        )

    def test_honey_diabetic_claim_missing(self):
        self.assertBlocked(
            'عسل دیابتی و درمانی چند گیاه با ساکاروز 1',
            'عسل طبیعی چند گیاه کوهی',
            'semantic_honey_claim_missing',
        )

    def test_fish_type_mismatch(self):
        self.assertBlocked('ماهی هوور تازه یک کیلو', 'ماهی حسون تازه یک کیلو', 'semantic_fish_type_mismatch')

    def test_dimension_mismatch_and_reversed_equivalence(self):
        self.assertBlocked('دریچه کولر سایز 25x40', 'دریچه کولر سایز 20 در 45', 'semantic_dimension_mismatch')
        self.assertNotBlocked('دریچه کولر سایز 25x40', 'دریچه کولر سایز 40 در 25', 'semantic_dimension_mismatch')

    def test_capacity_and_wattage_mismatch(self):
        self.assertBlocked('کولر گازی هایسنس 24 هزار', 'کولر گازی هایسنس 18 هزار', 'semantic_capacity_mismatch')
        self.assertBlocked('مینی فرز باس 1500 وات', 'مینی فرز باس 2500 وات', 'semantic_wattage_mismatch')

    def test_brand_mismatch(self):
        self.assertBlocked('مینی فرز باس 1500 وات', 'مینی فرز ماکیتا 1500 وات', 'semantic_brand_mismatch')

    def test_package_and_compartment_mismatch(self):
        self.assertBlocked('لوبیا چیتی بسته 10 عددی', 'لوبیا چیتی بسته 15 عددی', 'semantic_package_count_mismatch')
        self.assertBlocked('نظم دهنده کیف مدل 8 خانه', 'نظم دهنده کیف مدل 16 خانه', 'semantic_compartment_count_mismatch')

    def test_accessory_main_product_mismatch(self):
        self.assertBlocked(
            'دسته یدکی کنسول بازی Game Stick Lite 64GB',
            'کنسول بازی Game Stick Lite 64GB 4K',
            'semantic_accessory_main_mismatch',
        )

    def test_nut_mix_mismatch(self):
        self.assertBlocked('آجیل چهارمغز شور تازه', 'آجیل پنج مغز شور تازه', 'semantic_nut_mix_mismatch')


class ScoreCandidateSemanticBlockerTests(SimpleTestCase):
    def test_semantic_blocker_rejects_otherwise_valid_candidate(self):
        snapshot = SimpleNamespace(
            id=1,
            source_product_id=100,
            title='مینی فرز دسته بلند دیمردار 1500 وات اصلی باس',
            description='',
            summary='',
            category_title='ابزار',
            category_parent_title='ابزارآلات',
            navigation_slug='tools',
            attributes_text='',
            unit_type='عددی',
            unit_quantity=1,
            net_weight=0,
            price=1_000_000,
        )
        candidate = {
            'candidate_id': 200,
            'candidate_title': 'مینی فرز دسته بلند دیمردار 2500 وات اصلی باس',
            'candidate_description': '',
            'candidate_summary': '',
            'candidate_category_title': 'ابزار',
            'candidate_category_parent_title': 'ابزارآلات',
            'candidate_navigation_slug': 'tools',
            'candidate_attributes_text': '',
            'candidate_unit_type': 'عددی',
            'candidate_unit_quantity': 1,
            'candidate_net_weight': 0,
            'candidate_price': 900_000,
            'candidate_vendor_identifier': 'vendor',
        }
        config = AnalysisConfig(min_similarity=0.1, min_cheaper_delta=1)

        result = score_candidate(snapshot=snapshot, candidate=candidate, config=config)

        self.assertFalse(result.accepted)
        self.assertIn('semantic_wattage_mismatch', result.rejection_reasons)
        self.assertEqual(result.raw_candidate['semantic_cues']['source']['wattages'], [1500])
        self.assertEqual(result.raw_candidate['semantic_cues']['candidate']['wattages'], [2500])
        self.assertEqual(DailyProductSnapshot.AnalysisStatus.PENDING, 'analysis_pending')
