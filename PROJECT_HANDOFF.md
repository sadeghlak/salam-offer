# Salam Offer Project Handoff

> این فایل برای handoff بین چت‌ها/افراد ساخته شده است. بعد از هر تغییر مهم در معماری، منطق تحلیل، deploy، دیتابیس، worker، n8n یا UI باید به‌روزرسانی شود.
>
> **نکته امنیتی:** credential واقعی، password دیتابیس، token و secret را داخل این فایل commit نکنید. این فایل فقط نام envها، ساختار و روند deploy را توضیح می‌دهد.

## 1. هدف پروژه

`Salam Offer` یک پروژه Django برای پایش و تحلیل آفرهای روزانه باسلام است. ایده اصلی این است که محصولات Daily Off یا محصولات ورودی از workflowهای import ذخیره شوند، اطلاعات کامل محصول از API باسلام نگهداری شود، سپس موتور تحلیل بررسی کند آیا محصول مشابه ارزان‌تر معتبر در باسلام وجود دارد یا نه.

خروجی اصلی پروژه برای هر محصول:

- لینک‌های محصول مشابه ارزان‌تر (`product_url1`, `product_url2`, `product_url3`)
- تعداد کاندیدهای پذیرفته‌شده (`accepted_candidates_count`)
- وضعیت تحلیل (`analysis_pending`, `analysis_running`, `analyzed`, `no_match`, `analysis_error`)
- گزارش تصمیم‌گیری موتور تحلیل برای ساخت دیتاست قابل اصلاح توسط کاربر

## 2. مسیر پروژه و وضعیت Git

مسیر لوکال پروژه:

```text
D:\basalam\salam_offer
```

branchهای مهم:

- `main`: نسخه اصلی production تا قبل از تغییرات worker/report جدید.
- `salam-offer`: branch توسعه اصلی تغییرات جدید worker و گزارش تحلیل.
- `salam-test`: branch تست/staging که از `salam-offer` ساخته شده و برای بالا آوردن روی دامنه تستی استفاده می‌شود.
- `salam-offer-mvp`: branch قدیمی‌تر MVP/طراحی.

آخرین commitهای مهم تا زمان نوشتن این فایل:

```text
3e50af9 Add analysis decision dataset export
  - ذخیره candidateهای بررسی‌شده، قوانین رسمی واحدها، خروجی CSV اکسل

da51d80 Move product analysis to server worker queue
  - جدا کردن تحلیل از request مرورگر و انتقال پردازش به worker queue سمت سرور

8b3469e Update analysis results inline
  - نمایش inline نتیجه تحلیل در UI قبل از معماری worker

7f9e7bb Improve analysis failure visibility
  - لاگ‌گذاری بهتر تحلیل و خطاهای موتور

080ffb0 Move analysis workflow into Django
  - انتقال موتور تحلیل از n8n به Django
```

فایل‌های n8n زیر در محیط لوکال untracked بوده‌اند و عمداً commit نشده‌اند مگر کاربر صراحتاً بخواهد:

```text
basalam_vendor_discount_from_google_sheets_n8n.json
salam_offer_daily_off_import_n8n.json
```

## 3. معماری کلی

معماری فعلی شامل سه بخش است:

```text
Browser/User
   │
   ▼
Web Service (Django + Gunicorn)
   │  reads/writes
   ▼
PostgreSQL
   ▲
   │  reads pending jobs / writes results
Worker Service (Django management command)
```

### 3.1 Web Service

سرویس وب Django صفحات و APIها را serve می‌کند:

- dashboard
- run detail
- product detail
- APIهای import/analysis/status/export

فرمان معمول web همان اجرای gunicorn است که از Dockerfile/entrypoint پروژه اجرا می‌شود.

### 3.2 Worker Service

Worker یک سرویس جداست ولی از همان repo و همان branch استفاده می‌کند. این سرویس web server نیست و فقط command زیر را اجرا می‌کند:

```bash
python manage.py process_analysis_queue --loop --sleep 2 --limit 1
```

کار worker:

- خواندن snapshotهای `analysis_pending` از PostgreSQL
- claim کردن آن‌ها به `analysis_running`
- اجرای موتور تحلیل
- ذخیره نتیجه نهایی و گزارش candidateها در PostgreSQL
- ادامه کار حتی اگر کاربر browser را ببندد

اگر پلتفرم Container Port اجباری خواست، مقدار `8000` گذاشته شود ولی probeها برای worker disabled بمانند چون worker HTTP server ندارد.

### 3.3 PostgreSQL

Production و staging می‌توانند DB جدا داشته باشند. برای staging یک DB تستی ساخته شده است. credential واقعی نباید داخل repo نوشته شود.

Envهای لازم برای web/worker:

```env
DJANGO_DEBUG=0
DATABASE_SSL_REQUIRE=0
DATABASE_URL=<postgresql connection string>
DJANGO_ALLOWED_HOSTS=<domain>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<domain>
```

برای worker هم همان `DATABASE_URL` وب همان محیط باید استفاده شود تا هر دو به یک دیتابیس وصل باشند.

نکته Titan staging: اگر `DATABASE_URL` به host کوتاه stack مثل `data-test.salam-test.svc.cluster.local` اشاره کند و DNS resolve نشود، settings پروژه به‌صورت محافظه‌کارانه hostهای سرویس PostgreSQL HA همان stack (`*-postgresql-ha-pgpool`, `*-postgresql-ha-postgresql`, `*-postgresql-ha-keeper`) را امتحان می‌کند و فقط اگر یکی resolve شد همان را جایگزین می‌کند. راه‌حل ترجیحی بلندمدت همچنان تنظیم host درست در env است.

## 4. فایل‌ها و ماژول‌های اصلی

### 4.1 Models

فایل:

```text
daily_off/models.py
```

مدل‌های اصلی:

- `DailyRun`: اجرای روزانه، شامل `run_key`, `business_date`, status و شمارنده‌ها.
- `Product`: محصول یکتا براساس `basalam_product_id` و آخرین اطلاعات دیده‌شده.
- `DailyProductSnapshot`: snapshot محصول در یک run، شامل اطلاعات محصول، قیمت، فروشنده، وضعیت دریافت جزئیات و وضعیت تحلیل.
- `AnalysisStatusLog`: لاگ عملیاتی تحلیل برای trace وضعیت‌ها و خطاها.
- `AnalysisCandidate`: جدول گزارش تصمیم‌گیری تحلیل؛ هر row یک candidate بررسی‌شده برای یک snapshot است.

### 4.2 Services

فایل:

```text
daily_off/services.py
```

وظایف مهم:

- ingest محصول و ساخت/آپدیت `Product` و `DailyProductSnapshot`
- صف‌گذاری تحلیل (`enqueue_snapshot_analysis`)
- claim کردن pendingها (`claim_pending_analysis`)
- requeue کردن runningهای stale (`requeue_stale_analysis`)
- اجرای batch worker (`process_analysis_batch`)
- ذخیره نتیجه تحلیل (`store_analysis_result`)
- ذخیره candidate decision rows در `AnalysisCandidate`
- refresh وضعیت run

### 4.3 Analysis Engine

فایل:

```text
daily_off/analysis_engine.py
```

جریان تحلیل:

1. ساخت source context از snapshot
2. text search در باسلام
3. image search در صورت وجود عکس
4. merge/dedupe کاندیدها
5. اجرای Candidate Quality Filter محافظه‌کارانه قبل از detail fetch
6. fetch کردن detail فقط برای candidateهای passشده از OpenAPI باسلام
7. normalize کردن candidate detail
8. score کردن هر candidate
9. انتخاب acceptedها و ساخت `product_url1/2/3`
10. ساخت `AnalysisResult` شامل accepted و rejected candidates و metadata مربوط به prefilter

کلاس‌های مهم:

- `AnalysisConfig`
- `CandidateResult`
- `AnalysisResult`

### 4.4 Category Catalog and Family Router

فایل‌ها:

```text
daily_off/data/category_catalog.json
daily_off/category_catalog.py
daily_off/family_router.py
```

`category_catalog.json` از فایل `C:\Users\iliaco\Downloads\کتگوری ها.xlsx` ساخته شده و artifact پایدار داخل repo است؛ runtime نباید از Downloads بخواند. loader مسیر category را از `cat_leaf_title`، `cat_lvl3_title` یا `cat_lvl2_title` resolve می‌کند تا دسته‌هایی مثل `گوشی موبایل` که level3 خالی/غیرمستقل دارند هم درست route شوند.

Family Router فعلاً ساده و category-first است: ابتدا overrideهای level2 مثل `لوازم یدکی خودرو`، `لوازم جانبی خودرو`، `ابزار برقی`، `ابزار دستی`، `لوازم برقی` و `گوشی موبایل` را اعمال می‌کند؛ سپس mapping سطح ۱ به familyهایی مثل `food`، `digital`، `fashion`، `home_living`، `tools_auto` و غیره استفاده می‌شود. اگر category ناشناخته/عمومی باشد، title cues سبک به عنوان fallback استفاده می‌شوند و در نهایت `generic` با confidence پایین برمی‌گردد.

در موتور تحلیل، خروجی family routing فعلاً فقط در `raw_candidate.family_routing` ذخیره می‌شود و اثر محدود دارد: strictness مربوط به برند/وات/مدل فقط برای familyهای فنی (`tools`, `digital`, `home_appliance`, `tools_auto`, `auto_part`) یا generic فعال می‌شود تا false positiveهای حساس کاهش یابد بدون اینکه سیستم به ProductIdentity سنگین تبدیل شود.

### 4.5 Brand Catalog

فایل‌ها:

```text
daily_off/data/brand_catalog.json
daily_off/brand_catalog.py
```

`brand_catalog.json` از دو فایل Downloads ساخته شده است:

```text
C:\Users\iliaco\Downloads\Digital_Brands_200Plus.xlsx
C:\Users\iliaco\Downloads\Home_Appliance_Brands_250Plus.xlsx
```

ساختار هر row شامل `family`، `canonical_name`، `english_name`، `persian_name` و `aliases` است. فعلاً دو family پوشش داده شده‌اند: `digital` و `home_appliance`. هدف این است که اگر نام برند در عنوان محصول فارسی یا انگلیسی نوشته شده باشد، semantic brand detection همان canonical brand را تشخیص دهد؛ مثلاً `Apple` و `اپل` هر دو `Apple`، و `LG` / `ال جی` / `الجی` هر سه `LG` شوند.

`brand_catalog.py` aliasها را normalize و با patternهای safe روی متن title/attributes match می‌کند. این catalog در `semantic_rules.extract_cues(...)` استفاده می‌شود و در کنار aliasهای دستی قبلی، مقدار `brands` را پر می‌کند. Brand matching با family محدود می‌شود تا برندهای دیجیتال و لوازم خانگی بی‌دلیل روی familyهای غیرمرتبط اثر نگذارند؛ اما در family `generic` همچنان فعال است تا داده‌های category ناقص را پوشش دهد.

### 4.6 Unit Rules

فایل:

```text
daily_off/unit_rules.py
```

قوانین رسمی واحدهای باسلام برای تحلیل:

واحدهای مجاز:

- `عددی`
- `کیلوگرم`
- `گرم`
- `متر`
- `سانتی‌متر`
- `مثقال`

گروه‌ها:

- count: `عددی`
- weight: `کیلوگرم`, `گرم`, `مثقال`
- length: `متر`, `سانتی‌متر`

واحد مرجع:

- weight → گرم
- length → سانتی‌متر
- count → عددی

تبدیل‌ها:

```text
1 کیلوگرم = 1000 گرم
1 مثقال = 4.608 گرم
1 متر = 100 سانتی‌متر
```

قانون مقایسه:

- فقط واحدهای هم‌گروه قابل مقایسه‌اند.
- مقدار نرمال‌شده با tolerance یک درصد مقایسه می‌شود.
- فعلاً candidate فقط وقتی accepted می‌شود که مقدار معادل داشته باشد؛ price-per-unit برای مقدار متفاوت معیار acceptance نیست.
- measurement استخراج‌شده از title مثل `برنج 10 کیلوگرمی` signal کمکی/گزارشی است، ولی بدون احتیاط جایگزین فیلد رسمی API نمی‌شود.

### 4.7 Views and URLs

فایل‌ها:

```text
daily_off/views.py
daily_off/urls.py
```

صفحات:

- `/` dashboard
- `/runs/<run_key>/` run detail
- `/products/<product_id>/` product detail

APIهای مهم:

- `POST /api/runs/`
- `POST /api/runs/products/next-batch/`
- `POST /api/products/ingest/`
- `POST /api/products/error/`
- `POST /api/analysis/snapshots/<snapshot_id>/run/`
  - الان فقط snapshot را queue می‌کند، تحلیل را داخل request اجرا نمی‌کند.
- `GET /api/analysis/snapshots/<snapshot_id>/status/`
  - برای polling وضعیت تحلیل از UI.
- `GET /api/runs/<run_key>/analysis-status/`
  - برای وضعیت کلی run.
- `GET /runs/<run_key>/analysis-candidates/export.csv`
  - خروجی Excel-compatible برای گزارش کاربر از محصولات مرجع و سه محصول مشابه برتر.

### 4.8 Templates

فایل‌های اصلی:

```text
daily_off/templates/daily_off/base.html
daily_off/templates/daily_off/dashboard.html
daily_off/templates/daily_off/run_detail.html
daily_off/templates/daily_off/product_detail.html
```

نکات UI فعلی:

- `/` صفحه اصلی Salam Offer و Product Operations Workspace تیم Daily Off است، نه KPI/marketing/admin dashboard.
- تجربه اصلی برای اپراتوری روزانه ۵۰ تا ۳۰۰ محصول طراحی شده است؛ لیست محصولات اجرای امروز مهم‌ترین بخش صفحه است و بیشترین فضای viewport را می‌گیرد.
- چیدمان کلی workspace از مرجع تصویری فقط برای جاگیری کامپوننت‌ها الهام می‌گیرد: sidebar راست و مرکز table-first برای محصولات؛ پنل‌های context مثل Run Focus/Outputs از صفحه اصلی حذف شده‌اند چون اجراها و گزارش‌گیری در sidebar هستند.
- sidebar navigation حداقلی دارد: لوگوی Salam Offer، خانه، منوی آبشاری اجراها برای تغییر اجرای صفحه اصلی، و لینک گزارش‌گیری اجرای انتخاب‌شده. کارت‌های خلاصه/quick access در sidebar نمایش داده نمی‌شوند.
- اجرای امروز براساس `business_date` به صورت پیش‌فرض انتخاب می‌شود و اگر نبود آخرین اجرا باز می‌شود؛ `/runs/<run_key>/` همان workspace را با اجرای انتخاب‌شده باز می‌کند.
- بالای بخش اصلی یک منوی افقی placeholder قرار دارد تا فضای تنفسی بالای محصولات ایجاد شود؛ زیر آن toolbar فشرده برای Search، Filter و Sort قرار دارد.
- محصول‌ها با Data Table حرفه‌ای و فشرده نمایش داده می‌شوند: تصویر، نام محصول، فروشنده، قیمت اصلی، قیمت دیلی آف، درصد تخفیف، وضعیت و زمان اجرا.
- از کارت‌های بزرگ، widgets، summary cards و الگوی dashboard مدیریتی در صفحه اصلی استفاده نمی‌شود.
- عملکرد تحلیل، polling و خروجی اکسل در همین workspace حفظ شده است.
- product detail امکان queue کردن تحلیل محصول و polling دارد.
- خروجی‌ها و result links بعد از تحلیل از DB خوانده می‌شوند.

### 4.9 Worker Command

فایل:

```text
daily_off/management/commands/process_analysis_queue.py
```

فرمان:

```bash
python manage.py process_analysis_queue --loop --sleep 2 --limit 1
```

گزینه‌ها:

- `--loop`: اجرای دائمی
- `--sleep`: فاصله poll وقتی صف خالی است
- `--limit`: تعداد محصولات در هر batch
- `--run-key`: محدود کردن worker به یک run خاص
- `--today-only`: فقط امروز، اگر run-key داده نشده
- `--older-than-minutes`: requeue کردن runningهای stale
- `--actor`: نام actor برای logs

## 5. موتور تحلیل: قوانین فعلی acceptance/rejection

یک candidate وقتی accepted می‌شود که همه شرایط زیر برقرار باشد:

1. قیمت candidate موجود باشد.
2. candidate ارزان‌تر از source باشد و اختلاف حداقل برابر `CHEAPER_ANALYSIS_MIN_CHEAPER_DELTA` باشد.
3. score نهایی حداقل برابر `CHEAPER_ANALYSIS_MIN_SIMILARITY` باشد.
4. واحد source و candidate در یک گروه باشند.
5. مقدار نرمال‌شده source و candidate با tolerance یک درصد معادل باشد.
6. هیچ semantic blocker با اطمینان بالا بین source و candidate وجود نداشته باشد.

قبل از fetch کردن detail، Candidate Quality Filter محافظه‌کارانه اجرا می‌شود تا candidateهای واضحاً بد حذف شوند. در فاز ۱ فقط دو hard skip فعال است: قیمت search معتبر و گران‌تر/برابر محصول اصلی (`prefilter_not_cheaper`) و overlap صفر بین tokenهای عنوان source و candidate (`prefilter_title_overlap_too_low`). اگر قیمت candidate در search موجود نباشد یا یکی از titleها token قابل مقایسه نداشته باشد، candidate حذف نمی‌شود و برای detail fetch باقی می‌ماند. prefilter rejectedها فعلاً وارد `AnalysisCandidate` نمی‌شوند؛ فقط در analysis log و payload نتیجه با evidence سبک ذخیره می‌شوند.

لایه semantic blocker از annotationهای دیتاست دستی ساخته شده و بدون مدل جدید، تفاوت‌های صریح title/attribute را reject می‌کند: subtype عسل و claimهای دیابتی/ساکاروز، نوع ماهی، ابعاد، ظرفیت، وات، مدل، برند، عمده/بسته چندتایی، تعداد خانه، accessory در برابر محصول اصلی، ترکیب آجیل و mismatch صریح جنس/کیفیت. برای هر semantic blocker اکنون `SemanticComparison.evidence` ساخته می‌شود و داخل `raw_candidate.semantic_evidence` و `raw_candidate.semantic_cues.evidence` ذخیره می‌شود. این evidence شامل `reason_code`، severity/confidence، کلید cue و values استخراج‌شده source/candidate است. ارسال رایگان و رضایت مشتری فعلاً future work هستند و در scoring دخالت داده نمی‌شوند.

Family routing در `raw_candidate.family_routing` ذخیره می‌شود. اثر rule-level آن فعلاً محدود است: `semantic_brand_mismatch`، `semantic_wattage_mismatch` و `semantic_model_mismatch` فقط برای familyهای فنی یا generic اجرا می‌شوند؛ ruleهای food مثل honey/fish/nut و ruleهای اندازه/بسته‌بندی همچنان بر اساس cueهای explicit کار می‌کنند.

اگر هر شرط بعد از detail fetch برقرار نباشد، candidate rejected می‌شود و دلیل reject در `AnalysisCandidate.rejection_reasons` و `rejection_reason_text` ذخیره می‌شود.

دلایل reject فعلی:

- `candidate_price_missing`
- `not_cheaper`
- `similarity_below_threshold`
- `unit_missing`
- `unit_group_mismatch`
- `unit_quantity_mismatch`
- `semantic_brand_mismatch`
- `semantic_model_mismatch`
- `semantic_dimension_mismatch`
- `semantic_capacity_mismatch`
- `semantic_wattage_mismatch`
- `semantic_honey_subtype_mismatch`
- `semantic_honey_claim_missing`
- `semantic_fish_type_mismatch`
- `semantic_wholesale_mismatch`
- `semantic_package_count_mismatch`
- `semantic_compartment_count_mismatch`
- `semantic_accessory_main_mismatch`
- `semantic_nut_mix_mismatch`
- `semantic_material_mismatch`

## 6. گزارش کاربر

بعد از تحلیل یک run، از صفحه run detail دکمه زیر قابل استفاده است:

```text
خروجی اکسل محصولات مشابه
```

خروجی اکسل فعلی برای کاربر نهایی ساده شده و دیگر فرم annotation/dataset داخلی نیست. هر row یک محصول مرجع را همراه با قیمت Daily Off و سه محصول مشابه پذیرفته‌شده اول نشان می‌دهد. ستون‌ها:

```text
نام محصول مرجع
قیمت داخل دیلی آف
محصول مشابه ۱
محصول مشابه ۲
محصول مشابه ۳
```

نام محصول مرجع و محصولات مشابه در فایل Excel-compatible HTML به لینک محصول در باسلام تبدیل می‌شوند؛ اگر لینک candidate در `AnalysisCandidate.candidate_url` موجود نباشد، از `candidate_id` و `candidate_vendor_identifier` ساخته می‌شود. گزارش فنی کامل candidateها همچنان در جدول `AnalysisCandidate` ذخیره می‌شود، اما خروجی کاربر فقط گزارش خلاصه و قابل مصرف است.

## 7. n8n و import روزانه

قبلاً موتور تحلیل محصول در n8n بوده و حالا به Django منتقل شده است. n8n فعلاً برای import روزانه/دیلی‌آف می‌تواند باقی بماند.

نکته مهم برای staging/test:

- n8n اصلی production اگر به `https://salam-offer.titanapp.dev` می‌زند، دیتای تست را پر نمی‌کند.
- برای `salam-test` باید workflow کپی‌شده n8n با base URL دامنه تست ساخته شود.
- workflow اصلی production نباید به دامنه تست تغییر داده شود.

## 8. Deploy فعلی و محیط‌ها

### Production

- branch معمول: `main`
- دامنه اصلی: مثل `salam-offer.titanapp.dev`
- DB production: PostgreSQL production

### Staging/Test

- branch: `salam-test`
- DB تست: PostgreSQL جدا
- web تست و worker تست هر دو باید روی branch `salam-test` باشند.
- worker تست باید به همان DB تست وصل باشد.

نمونه تنظیمات worker:

```text
Start Command:
python manage.py process_analysis_queue --loop --sleep 2 --limit 1

Container Port:
8000

Readiness Probe:
Disabled

Liveness Probe:
Disabled
```

## 9. Migrationها

Migrationهای مهم اخیر:

- `0005_analysisstatuslog.py`: جدول لاگ تحلیل.
- `0006_analysiscandidate.py`: جدول candidateهای تصمیم‌گیری تحلیل.

بعد از deploy branchهای جدید باید migration اجرا شود. entrypoint پروژه معمولاً migrate را اجرا می‌کند. در log باید چیزی شبیه زیر دیده شود:

```text
Applying daily_off.0006_analysiscandidate... OK
```

## 10. روش تست end-to-end

برای تست کامل staging:

1. web تست روی branch `salam-test` deploy شود.
2. worker تست روی branch `salam-test` deploy شود.
3. هر دو به DB تست وصل باشند.
4. n8n test workflow دیتا را به دامنه تست ارسال کند یا چند محصول دستی ingest شود.
5. run detail باز شود.
6. با دکمه `تحلیل مجدد همه محصولات` کل محصولات قابل تحلیل run دوباره به صف بروند؛ حتی اگر قبلاً analyzed/no_match/error شده باشند، نتیجه قبلی و candidate rows آن‌ها پاک و وضعیتشان `analysis_pending` شود. snapshotهای در حال اجرا دست‌نخورده می‌مانند.
7. تحلیل محصول تکی هم از دکمه ردیف محصول قابل queue شدن است.
8. در log worker باید دیده شود:

```text
Analysis worker started loop=True ...
analysis batch started ... claimed=...
analysis snapshot finished snapshot_id=... status=... accepted=...
```

9. در UI وضعیت analysis از pending/running به analyzed/no_match/error تغییر کند.
10. خروجی اکسل محصولات مشابه گرفته شود.
11. فایل Excel باز شود و ستون‌های گزارش کاربرمحور و لینک‌های محصول درست دیده شوند.

## 11. نکات مهم برای ادامه توسعه

- بعد از هر تغییر مهم، همین فایل باید به‌روزرسانی شود.
- web و worker همیشه باید روی یک branch/version باشند.
- secret و password داخل repo نوشته نشود.
- برای تغییرات الگوریتمی بزرگ، ابتدا خروجی CSV از داده واقعی گرفته شود و با annotation کاربر tuning انجام شود.
- فعلاً UI/ظاهر اولویت دوم است؛ تمرکز اصلی افزایش دقت موتور تحلیل است.
- هر تغییر روی واحدها باید در `daily_off/unit_rules.py` و این فایل ثبت شود.
- هر تغییر روی logic acceptance/rejection باید در همین فایل توضیح داده شود.

## 12. وضعیت فعلی اولویت‌ها

اولویت‌های فعلی پروژه:

1. تقویت منطق موتور تحلیل با تمرکز روی precision و کاهش false positive.
2. Candidate Quality Filter فاز ۱ پیاده‌سازی شده است؛ قدم بعدی بررسی اثر آن روی داده واقعی و در صورت نیاز tuning محافظه‌کارانه است.
3. Evidence System اولیه برای semantic blockers پیاده‌سازی شده و evidence داخل `raw_candidate` ذخیره می‌شود؛ migration جدید فعلاً لازم نیست.
4. Category Catalog و Family Router ساده با artifact پایدار `daily_off/data/category_catalog.json` پیاده‌سازی شده‌اند.
5. دکمه تحلیل مجدد همه محصولات باید کل محصولات قابل تحلیل run را دوباره queue کند، حتی اگر قبلاً تحلیل شده باشند.
6. تست branch `salam-test` روی دامنه تستی و بررسی اثر تغییرات روی محصولات واقعی.
7. تحلیل تعدادی محصول، گرفتن خروجی گزارش، annotation انسانی، و تبدیل خطاهای پرتکرار به ruleهای جدید.

سطح دسترسی/OAuth فعلاً اولویت ۲ است و فقط وقتی کاربر صراحتاً بگوید وارد فاز auth/access می‌شویم.

## 13. نقشه دقیق فاز بعدی موتور تحلیل

برای جلوگیری از گم شدن تصمیم‌های این چت، نقشه‌ی اجرایی کامل فاز بعدی در فایل زیر ثبت شده است:

```text
NEXT_ANALYSIS_ENGINE_WORK.md
```

این فایل باید قبل از شروع هر کار جدید روی منطق تحلیل خوانده شود. محتوای آن شامل جزئیات ۱۰۰٪ کارهای بعدی است:

- وضعیت فعلی pipeline موتور تحلیل.
- هدف فاز بعدی و دلیل اینکه نباید وارد refactor سنگین یا ProductIdentity کامل شویم.
- جزئیات Candidate Quality Filter قبل از `fetch_candidate_detail`.
- طراحی Evidence System برای semantic blockers و prefilter decisions.
- روش تبدیل فایل `کتگوری ها.xlsx` به `daily_off/data/category_catalog.json`.
- طراحی Category Catalog و Simple Family Router.
- لیست familyهای اولیه و overrideهای level2.
- مواردی که فعلاً نباید انجام شوند، مثل ProductIdentity کامل، family profileهای زیاد، ML model جدید، migration evidence، یا ورود ارسال رایگان/رضایت مشتری به scoring.
- تست‌ها و verificationهای لازم.
- فایل‌هایی که احتمالاً باید تغییر یا اضافه شوند.

تصمیم‌های قطعی ثبت‌شده در آن فایل:

- پروژه در فاز Build → Improve است، نه Research → Build؛ سیستم فعلی کار می‌کند و باید incremental بهتر شود.
- خطر اصلی فاز فعلی complexity است، بنابراین تغییرات باید کم‌ریسک، قابل تست و قابل rollback باشند.
- Candidate Quality Filter، Evidence System اولیه، Category Catalog و Simple Family Router قبل از ProductIdentity کامل اجرا شده‌اند.
- Category باید first priority در routing باشد، ولی category-only نیست؛ title cues و attributes نقش fallback/support دارند.
- `cat_leaf_title` از فایل دسته‌بندی‌ها canonical category محصول محسوب می‌شود چون بعضی دسته‌ها مثل `گوشی موبایل` level3 ندارند.
- طبق درخواست جدید کاربر، اصلاحات بعدی فعلاً local نگه داشته می‌شوند و push فقط با دستور صریح کاربر انجام می‌شود.
