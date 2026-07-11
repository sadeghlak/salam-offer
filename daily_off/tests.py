from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase

from config.settings import database_url_with_resolvable_service_host

from .analysis_engine import AnalysisConfig, AnalysisResult, prefilter_candidates, score_candidate
from .category_catalog import resolve_category_path
from .family_router import route_family, route_product_family
from .product_identity import compare_product_identities, extract_product_identity, plan_search_queries
from .models import AnalysisCandidate, AnalysisStatusLog, DailyProductSnapshot, DailyRun, Product
from .semantic_rules import compare_semantic_cues
from .services import (
    analyze_test_product,
    fetch_test_product,
    process_analysis_batch,
    requeue_run_analysis,
    unwrap_product_detail_payload,
)
from .views import build_run_context, export_run_analysis_candidates_csv


class DatabaseUrlFallbackTests(SimpleTestCase):
    def test_rewrites_unresolvable_titan_postgres_stack_host_to_resolvable_service_host(self):
        database_url = 'postgresql://user:pass@data-test.salam-test.svc.cluster.local:5432/dbname'

        def fake_resolvable_host(hostname):
            return hostname == 'data-test-postgresql-ha-pgpool.salam-test.svc.cluster.local'

        with patch('config.settings.resolvable_host', side_effect=fake_resolvable_host):
            rewritten = database_url_with_resolvable_service_host(database_url)

        self.assertEqual(
            rewritten,
            'postgresql://user:pass@data-test-postgresql-ha-pgpool.salam-test.svc.cluster.local:5432/dbname',
        )

    def test_keeps_original_database_url_when_host_is_resolvable(self):
        database_url = 'postgresql://user:pass@db.example.com:5432/dbname'

        with patch('config.settings.resolvable_host', return_value=True):
            rewritten = database_url_with_resolvable_service_host(database_url)

        self.assertEqual(rewritten, database_url)


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

    def test_wattage_mismatch_has_structured_evidence(self):
        comparison = compare_semantic_cues(
            source_title='مینی فرز باس 1500 وات',
            source_text='مینی فرز باس 1500 وات',
            candidate_title='مینی فرز باس 2500 وات',
            candidate_text='مینی فرز باس 2500 وات',
        )

        self.assertIn('semantic_wattage_mismatch', comparison.blocker_reasons)
        evidence = [row for row in comparison.evidence if row['reason_code'] == 'semantic_wattage_mismatch'][0]
        self.assertEqual(evidence['key'], 'wattages')
        self.assertEqual(evidence['source']['values'], [1500])
        self.assertEqual(evidence['candidate']['values'], [2500])

    def test_brand_mismatch(self):
        self.assertBlocked('مینی فرز باس 1500 وات', 'مینی فرز ماکیتا 1500 وات', 'semantic_brand_mismatch')

    def test_digital_brand_persian_english_equivalence(self):
        comparison = compare_semantic_cues(
            source_title='گوشی موبایل Apple ظرفیت 128 گیگ',
            source_text='گوشی موبایل Apple ظرفیت 128 گیگ',
            candidate_title='گوشی موبایل اپل ظرفیت 128 گیگ',
            candidate_text='گوشی موبایل اپل ظرفیت 128 گیگ',
            source_family='digital',
            candidate_family='digital',
        )

        self.assertNotIn('semantic_brand_mismatch', comparison.blocker_reasons)
        self.assertEqual(comparison.details['source']['brands'], ['Apple'])
        self.assertEqual(comparison.details['candidate']['brands'], ['Apple'])

    def test_home_appliance_brand_persian_english_mismatch(self):
        comparison = compare_semantic_cues(
            source_title='تلویزیون ال جی 55 اینچ',
            source_text='تلویزیون ال جی 55 اینچ',
            candidate_title='تلویزیون Samsung 55 اینچ',
            candidate_text='تلویزیون Samsung 55 اینچ',
            source_family='home_appliance',
            candidate_family='home_appliance',
        )

        self.assertIn('semantic_brand_mismatch', comparison.blocker_reasons)
        evidence = [row for row in comparison.evidence if row['reason_code'] == 'semantic_brand_mismatch'][0]
        self.assertEqual(evidence['source']['values'], ['LG'])
        self.assertEqual(evidence['candidate']['values'], ['Samsung'])

    def test_digital_brand_mismatch(self):
        comparison = compare_semantic_cues(
            source_title='گوشی موبایل Apple ظرفیت 128 گیگ',
            source_text='گوشی موبایل Apple ظرفیت 128 گیگ',
            candidate_title='گوشی موبایل سامسونگ ظرفیت 128 گیگ',
            candidate_text='گوشی موبایل سامسونگ ظرفیت 128 گیگ',
            source_family='digital',
            candidate_family='digital',
        )

        self.assertIn('semantic_brand_mismatch', comparison.blocker_reasons)

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


class FamilyRouterTests(SimpleTestCase):
    def test_mobile_without_level3_routes_to_digital(self):
        category_path = resolve_category_path(category_title='گوشی موبایل')
        route = route_family(category_path, title='گوشی موبایل سامسونگ')

        self.assertEqual(category_path['leaf'], 'گوشی موبایل')
        self.assertEqual(category_path['lvl2'], 'گوشی موبایل')
        self.assertEqual(route['family'], 'digital')
        self.assertEqual(route['confidence'], 'high')

    def test_brake_pad_routes_to_auto_part(self):
        route = route_product_family(category_title='لنت ترمز خودرو', title='لنت ترمز جلو')

        self.assertEqual(route['family'], 'auto_part')
        self.assertEqual(route['confidence'], 'high')

    def test_water_cooler_routes_to_home_appliance(self):
        route = route_product_family(category_title='لوازم برقی', title='کولر آبی')

        self.assertEqual(route['family'], 'home_appliance')
        self.assertEqual(route['confidence'], 'high')

    def test_almond_routes_to_food(self):
        route = route_product_family(category_title='بادام درختی', title='بادام درختی تازه')

        self.assertEqual(route['family'], 'food')
        self.assertEqual(route['confidence'], 'high')

    def test_unknown_routes_to_generic_low_confidence(self):
        route = route_product_family(category_title='دسته ناموجود تستی', title='محصول نامشخص')

        self.assertEqual(route['family'], 'generic')
        self.assertEqual(route['confidence'], 'low')


class ProductIdentityTests(SimpleTestCase):
    def assertIdentityBlocked(self, source, candidate, reason, **kwargs):
        source_identity = extract_product_identity(title=source, text=source, **kwargs)
        candidate_identity = extract_product_identity(title=candidate, text=candidate, **kwargs)
        comparison = compare_product_identities(source_identity, candidate_identity)
        self.assertIn(reason, comparison.blockers)
        return comparison

    def test_person_capacity_mismatch_blocks_tent_matches(self):
        comparison = self.assertIdentityBlocked(
            'چادر مسافرتی 8 نفره مدل برزنت برنو بلیزر',
            'چادر مسافرتی 4 نفره مدل برزنت برنو بلیزر',
            'identity_person_capacity_mismatch',
            category_title='چادر مسافرتی',
        )

        self.assertEqual(comparison.evidence[0]['key'], 'person_counts')

    def test_food_variety_and_base_mismatches_are_blocked(self):
        self.assertIdentityBlocked(
            'پودر فلفل سیاه اعلا 100 گرمی',
            'پودر فلفل قرمز اعلا 100 گرمی',
            'identity_food_variety_mismatch',
            category_title='ادویه',
        )
        self.assertIdentityBlocked(
            'کره نارگیل 500 گرمی ارگانیک',
            'کره بادام زمینی 500 گرمی ارگانیک',
            'identity_food_base_mismatch',
            category_title='مواد غذایی',
        )
        self.assertIdentityBlocked(
            'آرد جو دوسر کامل 1 کیلویی',
            'آرد گندم کامل 1 کیلویی',
            'identity_food_base_mismatch',
            category_title='آرد',
        )

    def test_rice_form_and_variety_mismatches_are_blocked(self):
        self.assertIdentityBlocked(
            'برنج سرلاشه طارم هاشمی 10 کیلویی',
            'برنج نیم دانه فجر 10 کیلویی',
            'identity_food_variety_mismatch',
            category_title='برنج',
        )
        comparison = self.assertIdentityBlocked(
            'برنج سرلاشه طارم هاشمی 10 کیلویی',
            'برنج نیم دانه طارم هاشمی 10 کیلویی',
            'identity_food_form_mismatch',
            category_title='برنج',
        )
        self.assertIn('identity_food_form_mismatch', comparison.blockers)

    def test_model_and_capacity_mismatches_are_blocked(self):
        self.assertIdentityBlocked(
            'گوشی موبایل سامسونگ مدل GALAXY S26 Ultra ظرفیت 256 گیگ',
            'گوشی موبایل سامسونگ مدل Galaxy S25 Ultra ظرفیت 256 گیگ',
            'identity_model_mismatch',
            category_title='گوشی موبایل',
        )
        self.assertIdentityBlocked(
            'هارد اکسترنال 1 ترابایت وسترن دیجیتال',
            'هارد اکسترنال 500 گیگ وسترن دیجیتال',
            'identity_measurement_mismatch',
            category_title='کالای دیجیتال',
        )

    def test_same_identity_is_not_blocked(self):
        source_identity = extract_product_identity(
            title='هارد اکسترنال 500 گیگ وسترن دیجیتال المنت',
            text='هارد اکسترنال 500 گیگ وسترن دیجیتال المنت',
            category_title='کالای دیجیتال',
        )
        candidate_identity = extract_product_identity(
            title='هارد اکسترنال 500 گیگابایت مدل Element وسترن دیجیتال',
            text='هارد اکسترنال 500 گیگابایت مدل Element وسترن دیجیتال',
            category_title='کالای دیجیتال',
        )

        comparison = compare_product_identities(source_identity, candidate_identity)

        self.assertNotIn('identity_measurement_mismatch', comparison.blockers)
        self.assertNotIn('identity_low_anchor_overlap', comparison.blockers)


class QueryPlannerTests(SimpleTestCase):
    def test_query_planner_keeps_full_title_and_adds_identity_query(self):
        snapshot = SimpleNamespace(
            title='ایرپاد انکر مدل A2845 با گارانتی یک ساله ارسال رایگان',
            category_title='هندزفری بلوتوثی',
            category_parent_title='کالای دیجیتال',
            navigation_slug='',
            attributes_text='',
            description='',
            summary='',
            unit_type='عددی',
            unit_quantity=1,
            net_weight=0,
        )

        queries = plan_search_queries(snapshot, max_queries=4)
        query_texts = [query.query for query in queries]
        query_kinds = [query.kind for query in queries]

        self.assertIn('full_title', query_kinds)
        self.assertIn('identity_anchor', query_kinds)
        self.assertTrue(any('a2845' in text.lower() or 'A2845' in text for text in query_texts))
        self.assertFalse(any('ارسال رایگان' in text for text in query_texts))
        self.assertLessEqual(len(queries), 4)

    def test_query_planner_builds_food_identity_query(self):
        snapshot = SimpleNamespace(
            title='برنج سرلاشه طارم هاشمی 10 کیلویی ارسال رایگان',
            category_title='برنج',
            category_parent_title='مواد غذایی',
            navigation_slug='',
            attributes_text='',
            description='',
            summary='',
            unit_type='کیلوگرم',
            unit_quantity=10,
            net_weight=10,
        )

        queries = plan_search_queries(snapshot, max_queries=4)
        identity_queries = [query.query for query in queries if query.kind == 'identity_anchor']

        self.assertTrue(identity_queries)
        self.assertTrue(any('برنج' in query and ('طارم' in query or 'هاشمی' in query) for query in identity_queries))


class CandidatePrefilterTests(SimpleTestCase):
    def snapshot(self, title='مینی فرز باس 1500 وات', price=1_000_000):
        return SimpleNamespace(title=title, price=price)

    def test_candidate_with_valid_higher_search_price_is_rejected(self):
        candidates = [{
            'candidate_id': 200,
            'candidate_title': 'مینی فرز باس 1500 وات',
            'candidate_price': 1_200_000,
            'search_sources': ['text'],
        }]

        passed, rejected = prefilter_candidates(snapshot=self.snapshot(), candidates=candidates, config=AnalysisConfig())

        self.assertEqual(passed, [])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]['reason_code'], 'prefilter_not_cheaper')
        self.assertEqual(rejected[0]['evidence']['source']['price'], 1_000_000)
        self.assertEqual(rejected[0]['evidence']['candidate']['price'], 1_200_000)

    def test_candidate_without_search_price_is_not_rejected_by_price(self):
        candidates = [{
            'candidate_id': 200,
            'candidate_title': 'مینی فرز باس 1500 وات',
            'candidate_price': 0,
            'search_sources': ['text'],
        }]

        passed, rejected = prefilter_candidates(snapshot=self.snapshot(), candidates=candidates, config=AnalysisConfig())

        self.assertEqual(passed, candidates)
        self.assertEqual(rejected, [])

    def test_candidate_with_zero_title_overlap_is_rejected(self):
        candidates = [{
            'candidate_id': 200,
            'candidate_title': 'کفش ورزشی مردانه',
            'candidate_price': 900_000,
            'search_sources': ['image'],
        }]

        passed, rejected = prefilter_candidates(snapshot=self.snapshot(), candidates=candidates, config=AnalysisConfig())

        self.assertEqual(passed, [])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]['reason_code'], 'prefilter_title_overlap_too_low')
        self.assertEqual(rejected[0]['evidence']['title_overlap'], 0)

    def test_good_candidate_passes_prefilter(self):
        candidates = [{
            'candidate_id': 200,
            'candidate_title': 'مینی فرز باس 1500 وات دسته بلند',
            'candidate_price': 900_000,
            'search_sources': ['text'],
        }]

        passed, rejected = prefilter_candidates(snapshot=self.snapshot(), candidates=candidates, config=AnalysisConfig())

        self.assertEqual(passed, candidates)
        self.assertEqual(rejected, [])


class LevelOneCategoryFilterTests(TestCase):
    def test_run_context_filters_by_resolved_level_one_category(self):
        run = DailyRun.objects.create(business_date=date(2026, 6, 16), status=DailyRun.Status.RUNNING)
        digital_product = Product.objects.create(basalam_product_id=100, latest_title='گوشی')
        food_product = Product.objects.create(basalam_product_id=200, latest_title='بادام')
        DailyProductSnapshot.objects.create(
            run=run,
            product=digital_product,
            source_product_id=100,
            business_date=run.business_date,
            title='گوشی موبایل سامسونگ',
            category_title='گوشی موبایل',
        )
        DailyProductSnapshot.objects.create(
            run=run,
            product=food_product,
            source_product_id=200,
            business_date=run.business_date,
            title='بادام درختی تازه',
            category_title='بادام درختی',
        )

        request = RequestFactory().get('/', {'category_lvl1': 'کالای دیجیتال'})
        context = build_run_context(request, run)

        self.assertIn('کالای دیجیتال', context['category_lvl1_options'])
        self.assertIn('مواد غذایی', context['category_lvl1_options'])
        self.assertEqual(context['selected_category_lvl1'], 'کالای دیجیتال')
        self.assertEqual(context['shown_count'], 1)
        self.assertEqual(context['snapshots'][0].source_product_id, 100)
        self.assertEqual(context['snapshots'][0].category_lvl1_title, 'کالای دیجیتال')


class RequeueRunAnalysisTests(TestCase):
    def test_requeue_run_analysis_resets_finished_snapshots(self):
        run = DailyRun.objects.create(business_date=date(2026, 6, 16), status=DailyRun.Status.COMPLETED)
        product = Product.objects.create(basalam_product_id=100, latest_title='محصول مرجع')
        snapshot = DailyProductSnapshot.objects.create(
            run=run,
            product=product,
            source_product_id=100,
            business_date=run.business_date,
            title='محصول مرجع',
            price=1_000_000,
            analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED,
            status_row=DailyProductSnapshot.AnalysisStatus.ANALYZED,
            product_url1='https://basalam.com/a/product/1',
            accepted_candidates_count=1,
        )
        AnalysisCandidate.objects.create(
            snapshot=snapshot,
            run=run,
            product=product,
            candidate_id=200,
            candidate_title='محصول مشابه',
            candidate_price=900_000,
            decision=AnalysisCandidate.Decision.ACCEPTED,
        )

        run, queued_count = requeue_run_analysis(run_key=run.run_key, actor='test')
        snapshot.refresh_from_db()

        self.assertEqual(queued_count, 1)
        self.assertEqual(run.status, DailyRun.Status.RUNNING)
        self.assertIsNone(run.finished_at)
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.PENDING)
        self.assertEqual(snapshot.status_row, DailyProductSnapshot.AnalysisStatus.PENDING)
        self.assertEqual(snapshot.product_url1, '')
        self.assertEqual(snapshot.accepted_candidates_count, 0)
        self.assertFalse(AnalysisCandidate.objects.filter(snapshot=snapshot).exists())

    def test_requeue_run_analysis_keeps_running_snapshots_untouched(self):
        run = DailyRun.objects.create(business_date=date(2026, 6, 16), status=DailyRun.Status.RUNNING)
        product = Product.objects.create(basalam_product_id=100, latest_title='محصول مرجع')
        snapshot = DailyProductSnapshot.objects.create(
            run=run,
            product=product,
            source_product_id=100,
            business_date=run.business_date,
            title='محصول مرجع',
            analysis_status=DailyProductSnapshot.AnalysisStatus.RUNNING,
            status_row=DailyProductSnapshot.AnalysisStatus.RUNNING,
        )

        run, queued_count = requeue_run_analysis(run_key=run.run_key, actor='test')
        snapshot.refresh_from_db()

        self.assertEqual(queued_count, 0)
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.RUNNING)
        self.assertEqual(snapshot.status_row, DailyProductSnapshot.AnalysisStatus.RUNNING)


class ExportRunReportTests(TestCase):
    def test_export_user_report_has_simple_columns_and_links(self):
        run = DailyRun.objects.create(business_date=date(2026, 6, 16), status=DailyRun.Status.RUNNING)
        product = Product.objects.create(
            basalam_product_id=100,
            latest_title='محصول مرجع',
            latest_vendor_identifier='source-vendor',
        )
        snapshot = DailyProductSnapshot.objects.create(
            run=run,
            product=product,
            source_product_id=100,
            business_date=run.business_date,
            title='محصول مرجع',
            price=1_000_000,
            vendor_identifier='source-vendor',
            analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED,
        )
        AnalysisCandidate.objects.create(
            snapshot=snapshot,
            run=run,
            product=product,
            candidate_id=200,
            candidate_title='محصول مشابه اول',
            candidate_price=900_000,
            candidate_vendor_identifier='candidate-vendor',
            candidate_url='https://basalam.com/candidate-vendor/product/200',
            similarity_score=0.9,
            decision=AnalysisCandidate.Decision.ACCEPTED,
        )

        request = RequestFactory().get('/')
        response = export_run_analysis_candidates_csv(request, run.run_key)
        body = response.content.decode('utf-8')

        self.assertIn('salam-offer-report', response['Content-Disposition'])
        self.assertIn('نام محصول مرجع', body)
        self.assertIn('قیمت داخل دیلی آف', body)
        self.assertIn('محصول مشابه ۱', body)
        self.assertNotIn('نظر شما درباره مشابه', body)
        self.assertNotIn('محصول مشابه پیدا نشد؟', body)
        self.assertIn('href="https://basalam.com/source-vendor/product/100"', body)
        self.assertIn('href="https://basalam.com/candidate-vendor/product/200"', body)
        self.assertIn('محصول مشابه اول', body)


class ScoreCandidateSemanticBlockerTests(SimpleTestCase):
    def snapshot(self, **overrides):
        data = {
            'id': 1,
            'source_product_id': 100,
            'title': 'مینی فرز دسته بلند دیمردار 1500 وات اصلی باس',
            'description': '',
            'summary': '',
            'category_title': 'ابزار',
            'category_parent_title': 'ابزارآلات',
            'navigation_title': '',
            'navigation_slug': 'tools',
            'attributes_text': '',
            'unit_type': 'عددی',
            'unit_quantity': 1,
            'net_weight': 0,
            'price': 1_000_000,
        }
        data.update(overrides)
        return SimpleNamespace(**data)

    def candidate(self, **overrides):
        data = {
            'candidate_id': 200,
            'candidate_title': 'مینی فرز دسته بلند دیمردار 2500 وات اصلی باس',
            'candidate_description': '',
            'candidate_summary': '',
            'candidate_category_title': 'ابزار',
            'candidate_category_parent_title': 'ابزارآلات',
            'candidate_navigation_title': '',
            'candidate_navigation_slug': 'tools',
            'candidate_attributes_text': '',
            'candidate_unit_type': 'عددی',
            'candidate_unit_quantity': 1,
            'candidate_net_weight': 0,
            'candidate_price': 900_000,
            'candidate_vendor_identifier': 'vendor',
        }
        data.update(overrides)
        return data

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
        self.assertEqual(result.raw_candidate['semantic_evidence'][0]['reason_code'], 'semantic_wattage_mismatch')
        self.assertEqual(result.raw_candidate['family_routing']['source']['family'], 'tools')
        self.assertEqual(result.raw_candidate['family_routing']['candidate']['family'], 'tools')
        self.assertEqual(DailyProductSnapshot.AnalysisStatus.PENDING, 'analysis_pending')

    def test_identity_blocker_rejects_person_capacity_mismatch(self):
        snapshot = self.snapshot(
            title='چادر مسافرتی 8 نفره مدل برزنت برنو بلیزر',
            category_title='چادر مسافرتی',
            category_parent_title='خانه و آشپزخانه',
            navigation_slug='',
        )
        candidate = self.candidate(
            candidate_title='چادر مسافرتی 4 نفره مدل برزنت برنو بلیزر',
            candidate_category_title='چادر مسافرتی',
            candidate_category_parent_title='خانه و آشپزخانه',
            candidate_price=900_000,
        )
        config = AnalysisConfig(min_similarity=0.1, min_cheaper_delta=1)

        result = score_candidate(snapshot=snapshot, candidate=candidate, config=config)

        self.assertFalse(result.accepted)
        self.assertIn('identity_person_capacity_mismatch', result.rejection_reasons)
        self.assertIn('source_identity', result.raw_candidate)
        self.assertIn('candidate_identity', result.raw_candidate)
        self.assertIn('match_policy', result.raw_candidate)

    def test_identity_blocker_rejects_food_base_mismatch(self):
        snapshot = self.snapshot(
            title='کره نارگیل 500 گرمی ارگانیک',
            category_title='مواد غذایی',
            category_parent_title='خوراکی',
            navigation_slug='',
            unit_type='گرم',
            unit_quantity=500,
            net_weight=500,
        )
        candidate = self.candidate(
            candidate_title='کره بادام زمینی 500 گرمی ارگانیک',
            candidate_category_title='مواد غذایی',
            candidate_category_parent_title='خوراکی',
            candidate_unit_type='گرم',
            candidate_unit_quantity=500,
            candidate_net_weight=500,
            candidate_price=900_000,
        )
        config = AnalysisConfig(min_similarity=0.1, min_cheaper_delta=1)

        result = score_candidate(snapshot=snapshot, candidate=candidate, config=config)

        self.assertFalse(result.accepted)
        self.assertIn('identity_food_base_mismatch', result.rejection_reasons)
        self.assertIn('identity_food_base_mismatch', result.raw_candidate['match_policy']['blockers'])

    def test_identity_blocker_rejects_model_mismatch(self):
        snapshot = self.snapshot(
            title='گوشی موبایل سامسونگ مدل GALAXY S26 Ultra ظرفیت 256 گیگ',
            category_title='گوشی موبایل',
            category_parent_title='کالای دیجیتال',
            navigation_slug='',
        )
        candidate = self.candidate(
            candidate_title='گوشی موبایل سامسونگ مدل Galaxy S25 Ultra ظرفیت 256 گیگ',
            candidate_category_title='گوشی موبایل',
            candidate_category_parent_title='کالای دیجیتال',
            candidate_price=900_000,
        )
        config = AnalysisConfig(min_similarity=0.1, min_cheaper_delta=1)

        result = score_candidate(snapshot=snapshot, candidate=candidate, config=config)

        self.assertFalse(result.accepted)
        self.assertIn('identity_model_mismatch', result.rejection_reasons)

    def test_good_same_identity_candidate_can_still_be_accepted(self):
        snapshot = self.snapshot(
            title='هارد اکسترنال 500 گیگ وسترن دیجیتال المنت',
            category_title='کالای دیجیتال',
            category_parent_title='کالای دیجیتال',
            navigation_slug='',
            unit_type='عددی',
            unit_quantity=1,
            net_weight=0,
            price=1_000_000,
        )
        candidate = self.candidate(
            candidate_title='هارد اکسترنال 500 گیگابایت مدل Element وسترن دیجیتال',
            candidate_category_title='کالای دیجیتال',
            candidate_category_parent_title='کالای دیجیتال',
            candidate_unit_type='عددی',
            candidate_unit_quantity=1,
            candidate_net_weight=0,
            candidate_price=900_000,
        )
        config = AnalysisConfig(min_similarity=0.1, min_cheaper_delta=1)

        result = score_candidate(snapshot=snapshot, candidate=candidate, config=config)

        self.assertTrue(result.accepted)
        self.assertEqual(result.rejection_reasons, [])


class SnapshotAnalysisQueueApiTests(TestCase):
    def make_snapshot(self, *, analysis_status=DailyProductSnapshot.AnalysisStatus.PENDING, fetch_status=DailyProductSnapshot.FetchStatus.DETAILS_FETCHED):
        run = DailyRun.objects.create(business_date=date(2026, 7, 9), status=DailyRun.Status.RUNNING)
        product = Product.objects.create(basalam_product_id=9001, latest_title='source product')
        return DailyProductSnapshot.objects.create(
            run=run,
            product=product,
            source_product_id=9001,
            business_date=run.business_date,
            title='source product one piece',
            price=1_000_000,
            unit_type='عددی',
            unit_quantity=1,
            fetch_status=fetch_status,
            analysis_status=analysis_status,
            status_row=analysis_status,
            product_url1='https://basalam.com/source/product/1' if analysis_status == DailyProductSnapshot.AnalysisStatus.ANALYZED else '',
            accepted_candidates_count=1 if analysis_status == DailyProductSnapshot.AnalysisStatus.ANALYZED else 0,
        )

    @patch('daily_off.services.process_analysis_snapshot')
    @patch('daily_off.analysis_engine.analyze_snapshot')
    def test_snapshot_analysis_endpoint_queues_without_direct_processing(self, analyze_snapshot_mock, process_snapshot_mock):
        snapshot = self.make_snapshot()

        response = self.client.post(
            f'/api/analysis/snapshots/{snapshot.id}/run/',
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['queued'])
        self.assertEqual(payload['queue_state'], 'queued')
        self.assertNotIn('inline_processed', payload)
        analyze_snapshot_mock.assert_not_called()
        process_snapshot_mock.assert_not_called()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.PENDING)

    @patch('daily_off.analysis_engine.analyze_snapshot')
    def test_running_snapshot_without_force_is_not_requeued_or_processed(self, analyze_snapshot_mock):
        snapshot = self.make_snapshot(analysis_status=DailyProductSnapshot.AnalysisStatus.RUNNING)

        response = self.client.post(
            f'/api/analysis/snapshots/{snapshot.id}/run/',
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['queued'])
        self.assertEqual(payload['queue_state'], 'already_running')
        analyze_snapshot_mock.assert_not_called()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.RUNNING)

    @patch('daily_off.analysis_engine.analyze_snapshot')
    def test_finished_snapshot_without_force_is_not_requeued_or_processed(self, analyze_snapshot_mock):
        snapshot = self.make_snapshot(analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED)

        response = self.client.post(
            f'/api/analysis/snapshots/{snapshot.id}/run/',
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['queued'])
        self.assertEqual(payload['queue_state'], 'already_finished')
        analyze_snapshot_mock.assert_not_called()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.ANALYZED)

    def test_finished_snapshot_with_force_is_reset_to_pending(self):
        snapshot = self.make_snapshot(analysis_status=DailyProductSnapshot.AnalysisStatus.ANALYZED)

        response = self.client.post(
            f'/api/analysis/snapshots/{snapshot.id}/run/',
            data='{"force": true}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload['queued'])
        self.assertEqual(payload['queue_state'], 'queued')
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.PENDING)
        self.assertEqual(snapshot.status_row, DailyProductSnapshot.AnalysisStatus.PENDING)
        self.assertEqual(snapshot.product_url1, '')
        self.assertEqual(snapshot.accepted_candidates_count, 0)

    def test_snapshot_without_fetched_details_returns_bad_request(self):
        snapshot = self.make_snapshot(fetch_status=DailyProductSnapshot.FetchStatus.FETCH_ERROR)

        response = self.client.post(
            f'/api/analysis/snapshots/{snapshot.id}/run/',
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'snapshot details are not fetched')

    def test_missing_snapshot_returns_not_found(self):
        response = self.client.post(
            '/api/analysis/snapshots/999999/run/',
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    @patch('daily_off.analysis_engine.analyze_snapshot')
    def test_worker_batch_claims_and_processes_pending_snapshot(self, analyze_snapshot_mock):
        snapshot = self.make_snapshot()
        analyze_snapshot_mock.return_value = AnalysisResult(
            snapshot_id=snapshot.id,
            product_id=snapshot.source_product_id,
            analysis_status=DailyProductSnapshot.AnalysisStatus.NO_MATCH,
            status_row=DailyProductSnapshot.AnalysisStatus.NO_MATCH,
        )

        result = process_analysis_batch(run_key=str(snapshot.run.run_key), limit=1, actor='test_worker')

        self.assertTrue(result['ok'])
        self.assertEqual(result['processed_count'], 1)
        self.assertEqual(result['success_count'], 1)
        analyze_snapshot_mock.assert_called_once()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.analysis_status, DailyProductSnapshot.AnalysisStatus.NO_MATCH)
        self.assertTrue(AnalysisStatusLog.objects.filter(snapshot=snapshot, actor='test_worker').exists())


class ManualProductLabServiceTests(SimpleTestCase):
    databases = []

    def test_unwrap_product_detail_payload_supports_common_shapes(self):
        self.assertEqual(unwrap_product_detail_payload({'id': 1})['id'], 1)
        self.assertEqual(unwrap_product_detail_payload({'data': {'id': 2}})['id'], 2)
        self.assertEqual(unwrap_product_detail_payload({'result': {'id': 3}})['id'], 3)
        self.assertEqual(unwrap_product_detail_payload({'product': {'id': 4}})['id'], 4)

    @patch('daily_off.services.fetch_product_detail')
    def test_fetch_test_product_only_fetches_product_without_database_access(self, fetch_product_detail):
        fetch_product_detail.return_value = {
            'id': 100,
            'title': 'زعفران تست یک گرم',
            'price': 900000,
            'primary_price': 1000000,
            'category': {'title': 'زعفران'},
            'vendor': {'identifier': 'test-vendor', 'title': 'غرفه تست'},
            'unit_type': {'name': 'گرم'},
            'net_weight': 1,
        }

        result = fetch_test_product(product_id=100)

        self.assertTrue(result['ok'])
        self.assertEqual(result['snapshot'].source_product_id, 100)
        self.assertIsNone(result['result'])
        self.assertIsNone(result['result_payload'])

    @patch('daily_off.analysis_engine.fetch_candidate_detail')
    @patch('daily_off.analysis_engine.search_by_image', return_value=[])
    @patch('daily_off.analysis_engine.search_by_text', return_value=[])
    @patch('daily_off.services.fetch_product_detail')
    def test_test_product_analysis_does_not_use_database(self, fetch_product_detail, search_by_text, search_by_image, fetch_candidate_detail):
        fetch_product_detail.return_value = {
            'id': 100,
            'title': 'زعفران تست یک گرم',
            'price': 900000,
            'primary_price': 1000000,
            'category': {'title': 'زعفران'},
            'vendor': {'identifier': 'test-vendor', 'title': 'غرفه تست'},
            'unit_type': {'name': 'گرم'},
            'net_weight': 1,
        }

        result = analyze_test_product(product_id=100)

        self.assertTrue(result['ok'])
        self.assertEqual(result['snapshot'].source_product_id, 100)
        self.assertEqual(result['result_payload']['analysis_status'], DailyProductSnapshot.AnalysisStatus.NO_MATCH)


class ManualProductLabTests(TestCase):
    @patch('daily_off.views.fetch_test_product')
    def test_dashboard_test_product_tab_renders_without_manual_page(self, fetch_test_product_mock):
        snapshot = SimpleNamespace(
            source_product_id=200,
            title='محصول تست',
            price=500000,
            primary_price=600000,
            photo_url='',
            category_title='زعفران',
            vendor_name='غرفه تست',
            vendor_identifier='test-vendor',
            weight_text='1 گرم',
        )
        fetch_test_product_mock.return_value = {
            'ok': True,
            'request_id': 'req-test',
            'snapshot': snapshot,
            'product_url': 'https://basalam.com/test-vendor/product/200',
            'result': None,
            'result_payload': None,
        }

        response = self.client.post('/test-product/', {'action': 'fetch_test_product', 'product_id': '200'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'تست محصول')
        self.assertContains(response, 'محصول تست')
        self.assertNotContains(response, '/manual-analysis/')

    def test_daily_off_run_creation_still_uses_default_source_type(self):
        response = self.client.post(
            '/api/runs/',
            data='{"business_date": "2026-07-02", "input_count": 2}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        run = DailyRun.objects.get(business_date=date(2026, 7, 2), source_type='daily_off_query')
        self.assertEqual(run.input_count, 2)
