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
5. fetch کردن detail هر candidate از OpenAPI باسلام
6. normalize کردن candidate detail
7. score کردن هر candidate
8. انتخاب acceptedها و ساخت `product_url1/2/3`
9. ساخت `AnalysisResult` شامل accepted و rejected candidates

کلاس‌های مهم:

- `AnalysisConfig`
- `CandidateResult`
- `AnalysisResult`

### 4.4 Unit Rules

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

### 4.5 Views and URLs

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
  - خروجی Excel-compatible CSV از گزارش candidateهای تحلیل.

### 4.6 Templates

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
- چیدمان کلی workspace از الگوی سه‌ناحیه‌ای الهام می‌گیرد: sidebar راست، مرکز table-first برای محصولات، و support panel سمت چپ برای context اجرای جاری؛ مرجع تصویری فقط برای جاگیری کامپوننت‌هاست، نه بازسازی file manager.
- sidebar فقط navigation حداقلی دارد: لوگوی Salam Offer و خانه. لیست اجراها/کارت‌های خلاصه/quick access در sidebar نمایش داده نمی‌شوند.
- اجرای امروز براساس `business_date` به صورت پیش‌فرض انتخاب می‌شود و اگر نبود آخرین اجرا باز می‌شود؛ `/runs/<run_key>/` همان workspace را با اجرای انتخاب‌شده باز می‌کند.
- بالای بخش اصلی یک toolbar فشرده برای Search، Filter، Sort، Reports و Analytics قرار دارد.
- محصول‌ها با Data Table حرفه‌ای و فشرده نمایش داده می‌شوند: تصویر، نام محصول، فروشنده، قیمت اصلی، قیمت دیلی آف، درصد تخفیف، وضعیت و زمان اجرا.
- از کارت‌های بزرگ، widgets، summary cards و الگوی dashboard مدیریتی در صفحه اصلی استفاده نمی‌شود.
- عملکرد تحلیل، polling و خروجی اکسل در همین workspace حفظ شده است.
- product detail امکان queue کردن تحلیل محصول و polling دارد.
- خروجی‌ها و result links بعد از تحلیل از DB خوانده می‌شوند.

### 4.7 Worker Command

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

اگر هر شرط برقرار نباشد، candidate rejected می‌شود و دلیل reject در `AnalysisCandidate.rejection_reasons` و `rejection_reason_text` ذخیره می‌شود.

دلایل reject فعلی:

- `candidate_price_missing`
- `not_cheaper`
- `similarity_below_threshold`
- `unit_missing`
- `unit_group_mismatch`
- `unit_quantity_mismatch`

## 6. گزارش و دیتاست قابل اصلاح

بعد از تحلیل یک run، از صفحه run detail دکمه زیر قابل استفاده است:

```text
خروجی اکسل گزارش تحلیل
```

خروجی CSV فعلی عمداً ساده و سریع طراحی شده تا برای ساخت دیتاست دستی قابل فهم باشد. هر row یک محصول اصلی است و فقط سه خروجی پذیرفته‌شده اول را نشان می‌دهد، نه همه candidateهای rejectشده. ستون‌ها:

```text
اسم محصول اصلی
اسم محصول مشابه ۱
نظر شما درباره مشابه ۱
دلیل نظر درباره مشابه ۱
اسم محصول مشابه ۲
نظر شما درباره مشابه ۲
دلیل نظر درباره مشابه ۲
اسم محصول مشابه ۳
نظر شما درباره مشابه ۳
دلیل نظر درباره مشابه ۳
محصول مشابه پیدا نشد؟
اگر محصول مشابه صحیح دیگری مدنظر است، نام یا لینک آن را بنویسید
توضیحات کلی شما
```

هدف این است که کاربر گزارش مثلاً ۱۰۰ محصول را خروجی بگیرد، در Excel اصلاح کند و برای هر مشابه بنویسد درست/غلط است و چرا، یا اگر محصول مشابه صحیحی جا افتاده آن را ثبت کند. گزارش فنی کامل candidateها همچنان در جدول `AnalysisCandidate` ذخیره می‌شود، ولی خروجی CSV فعلاً human-friendly و dataset-oriented است.

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
6. تحلیل محصول queue شود.
7. در log worker باید دیده شود:

```text
Analysis worker started loop=True ...
analysis batch started ... claimed=...
analysis snapshot finished snapshot_id=... status=... accepted=...
```

8. در UI وضعیت analysis از pending/running به analyzed/no_match/error تغییر کند.
9. خروجی CSV گزارش تحلیل گرفته شود.
10. CSV در Excel باز شود و ستون‌های فارسی و `human_*` درست دیده شوند.

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

1. تست branch `salam-test` روی دامنه تستی.
2. اطمینان از کارکرد web + worker + DB تست.
3. اجرای n8n test import روی دامنه تست.
4. تحلیل تعدادی محصول و گرفتن CSV گزارش.
5. کاربر CSV را اصلاح کند و دیتاست اولیه را بدهد.
6. براساس دیتاست، tuning موتور تحلیل شروع شود.
