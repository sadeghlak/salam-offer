# Next Analysis Engine Work Plan

> این فایل برای ادامه کار در صورت بسته‌شدن چت ساخته شده است. هدف این است که دقیقاً مشخص باشد فاز بعدی تقویت منطق موتور تحلیل Salam Offer چیست، چرا انجام می‌شود، ترتیب اجرای آن چیست، چه فایل‌هایی باید تغییر کنند، و خروجی قابل قبول هر مرحله چیست.
>
> **وضعیت:** این فایل هنوز اجرای فنی نیست؛ نقشه‌ی کار فاز بعدی است. بعد از شروع پیاده‌سازی، هر تصمیم جدید یا تغییر مسیر باید همین‌جا و در `PROJECT_HANDOFF.md` ثبت شود.

## 1. وضعیت فعلی موتور تحلیل

موتور فعلی در `daily_off/analysis_engine.py` این pipeline را دارد:

```text
Source Snapshot
  ↓
Text Search + Image Search
  ↓
Merge / Dedupe Candidates
  ↓
Fetch Candidate Detail
  ↓
Normalize Candidate Detail
  ↓
Score Candidate
  ↓
Unit Rules + Semantic Blockers + Price Check
  ↓
Accepted / Rejected Candidates
```

اجزای موجود:

- `text_search_candidates`: جستجوی متنی در باسلام.
- `image_search_candidates`: جستجوی تصویری در صورت وجود عکس.
- `dedupe_candidates`: حذف تکراری‌ها و حذف خود محصول.
- `fetch_candidate_detail`: گرفتن detail کامل هر candidate از API باسلام.
- `normalize_candidate_detail`: نرمال‌سازی اطلاعات candidate.
- `score_candidate`: محاسبه similarity و تصمیم acceptance/rejection.
- `unit_rules.py`: مقایسه واحد، وزن، مقدار و title measurement.
- `semantic_rules.py`: blockerهای semantic که از دیتاست دستی استخراج شده‌اند.
- `AnalysisCandidate`: ذخیره accepted/rejected candidates و دلایل تصمیم.

شرط accept فعلی:

```text
candidate price exists
AND candidate is cheaper enough
AND final score >= threshold
AND unit group comparable
AND normalized unit quantity equivalent
AND no high-confidence semantic blocker
```

## 2. هدف فاز بعدی

هدف این فاز، بازنویسی بزرگ موتور نیست. هدف این است که با کمترین پیچیدگی، precision و قابلیت debug را بالا ببریم.

خطر اصلی در این مرحله **complexity** است، نه صرفاً accuracy. سیستم فعلی کار می‌کند، بنابراین تغییرات باید incremental و قابل اندازه‌گیری باشند.

فاز بعدی باید این سه قابلیت را اضافه کند:

1. **Candidate Quality Filter** قبل از `fetch_candidate_detail`
2. **Evidence System** برای ثبت دقیق چرایی رد/قبول یا prefilter
3. **Simple Family Router** با استفاده از فایل دسته‌بندی‌ها

فعلاً نباید وارد ProductIdentity کامل یا ده‌ها family/subfamily شویم.

## 3. فایل category mapping

فایل مرجع دسته‌بندی در Downloads کاربر است:

```text
C:\Users\iliaco\Downloads\کتگوری ها.xlsx
```

ساختار فایل:

```text
cat_lvl1_title
cat_lvl1_id
cat_lvl2_title
cat_lvl2_id
cat_lvl3_title
cat_lvl3_id
cat_leaf_title
```

نکته مهم:

- `cat_leaf_title` همان category نهایی است که روی محصول می‌افتد.
- بعضی دسته‌ها level 3 ندارند؛ مثلاً `گوشی موبایل` خودش level 2 است ولی leaf محصول هم همان است.
- پس در routing نباید فقط به `cat_lvl3_title` تکیه شود.
- category path باید از leaf به parentها resolve شود:

```json
{
  "leaf": "گوشی موبایل",
  "lvl3": "",
  "lvl2": "گوشی موبایل",
  "lvl1": "کالای دیجیتال"
}
```

یا:

```json
{
  "leaf": "لنت ترمز خودرو",
  "lvl3": "لنت ترمز خودرو",
  "lvl2": "لوازم یدکی خودرو",
  "lvl1": "ابزارآلات و تجهیزات خودرو"
}
```

این فایل نباید در runtime از Downloads خوانده شود. باید به artifact پایدار داخل repo تبدیل شود، مثلاً:

```text
daily_off/data/category_catalog.json
```

## 4. اولویت نهایی کارها

ترتیب اجرای پیشنهادی:

```text
Task 1: Candidate Quality Filter — انجام شد در فاز ۱
Task 2: Evidence System
Task 3: Category Catalog + Simple Family Router
Task 4: استفاده محدود از family در filter/rules
Task 5: بعد از جمع شدن داده، Attribute Extractor / ProductIdentity
```

فعلاً Task 5 اجرا نمی‌شود مگر بعد از بررسی داده‌های جدید.

## 5. Task 1 — Candidate Quality Filter

### 5.1 هدف

**وضعیت فاز ۱: انجام شد.** پیاده‌سازی فعلی محافظه‌کارانه است و فقط hard skipهای واضح را قبل از `fetch_candidate_detail` اعمال می‌کند.

قبل از اینکه برای هر candidate هزینه‌ی `fetch_candidate_detail` بدهیم، candidateهای واضحاً بد را حذف یا پایین‌اولویت کنیم.

وضع فعلی:

```text
Dedupe Candidates
  ↓
Fetch Detail for first N candidates
```

وضع مطلوب:

```text
Dedupe Candidates
  ↓
Candidate Quality Filter / Ranker
  ↓
Fetch Detail only for passed/top candidates
```

### 5.2 محل پیاده‌سازی

فایل اصلی:

```text
daily_off/analysis_engine.py
```

بعد از `dedupe_candidates(...)` و قبل از `fetch_candidate_detail(...)`.

در تابع `analyze_snapshot(...)` فعلی، بعد از dedupe، candidateها detail fetch می‌شوند. همان‌جا باید prefilter اضافه شود.

### 5.3 تابع پیشنهادی

```python
def prefilter_candidates(*, snapshot, candidates, config):
    ...
```

خروجی پیشنهادی:

```python
{
    "passed": [...],
    "rejected": [...],
    "rows": [...]
}
```

یا اگر ساده‌تر خواستیم:

```python
passed_candidates, prefilter_rejections = prefilter_candidates(...)
```

### 5.4 قوانین hard skip اولیه

قوانین hard skip باید محافظه‌کارانه باشند.

#### قانون 1: قیمت search معتبر و ارزان‌تر نیست

اگر `candidate_price` از search موجود و مثبت است و:

```python
candidate_price >= snapshot.price
```

و `snapshot.price` معتبر است، candidate لازم نیست detail fetch شود.

Reason code:

```text
prefilter_not_cheaper
```

Evidence:

```json
{
  "source_price": 1000000,
  "candidate_price": 1200000
}
```

نکته: اگر candidate price در search موجود نیست، حذف نشود؛ چون ممکن است detail قیمت معتبر بدهد.

#### قانون 2: title overlap بسیار پایین

اگر token overlap عنوان source و candidate خیلی پایین است، candidate حذف شود.

پیشنهاد اولیه:

```python
title_overlap < 0.08
```

یا conservativeتر:

```python
title_overlap == 0
```

Reason code:

```text
prefilter_title_overlap_too_low
```

Evidence:

```json
{
  "source_title_tokens": [...],
  "candidate_title_tokens": [...],
  "title_overlap": 0.0
}
```

#### قانون 3: category کاملاً غیرمرتبط

این قانون فقط بعد از Category Catalog / Family Router قابل اعتماد می‌شود. در Task 1 می‌تواند disabled بماند یا فقط به عنوان soft rank استفاده شود.

Reason code آینده:

```text
prefilter_category_family_mismatch
```

### 5.5 Soft ranking

به جای حذف گسترده، بهتر است candidateها rank شوند.

سیگنال‌های ranking ساده:

- search rank فعلی
- title overlap
- candidate cheaper بودن
- category/category title overlap اگر موجود بود
- semantic cues مثبت اگر سبک بود

پیشنهاد: در فاز اول فقط hard skip + حفظ order فعلی کافی است. اگر داده نشان داد نیاز است، ranking اضافه شود.

### 5.6 ذخیره prefilter rejected candidates

دو انتخاب داریم:

#### گزینه ساده‌تر

Prefilter rejectedها فقط در log ذخیره شوند و وارد `AnalysisCandidate` نشوند.

مزیت: migration و مدل جدید نمی‌خواهد.

#### گزینه بهتر برای audit

Prefilter rejectedها هم به عنوان `AnalysisCandidate` با decision rejected ذخیره شوند، اما چون detail ندارند ممکن است فیلدهای candidate کامل نباشد.

برای فاز اول پیشنهاد: **فقط log و raw analysis result metadata**. بعداً اگر لازم شد در جدول ذخیره شوند.

### 5.7 نتیجه اجرای فاز ۱

در فاز ۱ موارد زیر پیاده‌سازی شد:

- `title_token_overlap(...)` برای سنجش overlap ساده tokenهای عنوان.
- `prefilter_candidates(...)` در `daily_off/analysis_engine.py` بعد از dedupe و قبل از detail fetch.
- hard skip `prefilter_not_cheaper` وقتی `snapshot.price` و `candidate_price` معتبر باشند و candidate ارزان‌تر نباشد.
- hard skip `prefilter_title_overlap_too_low` وقتی هر دو title token داشته باشند و overlap صفر باشد.
- candidate بدون قیمت search یا title بدون token قابل مقایسه حذف نمی‌شود تا ریسک false negative کم بماند.
- prefilter rejectedها در log و `AnalysisResult.to_payload()` با `candidate_prefilter_rejected_count` و `candidate_prefilter_rejections` ذخیره می‌شوند، اما وارد `AnalysisCandidate` نمی‌شوند.
- تست‌های `CandidatePrefilterTests` در `daily_off/tests.py` اضافه شد.

Verification فاز ۱:

```powershell
& "D:\basalam\salam_offer\.venv\Scripts\python.exe" "D:\basalam\salam_offer\manage.py" test daily_off.tests
& "D:\basalam\salam_offer\.venv\Scripts\python.exe" "D:\basalam\salam_offer\manage.py" check
```

هر دو command بدون خطا pass شدند.

## 6. Task 2 — Evidence System

**وضعیت: انجام شد.** Evidence اولیه بدون migration پیاده‌سازی شده و داخل `raw_candidate` ذخیره می‌شود.

### 6.1 هدف

هر reason code باید evidence قابل خواندن داشته باشد. الان `semantic_wattage_mismatch` داریم، ولی باید بدانیم:

```json
{
  "source": 1500,
  "candidate": 2500
}
```

### 6.2 محل پیاده‌سازی

فایل‌های اصلی:

```text
daily_off/semantic_rules.py
daily_off/analysis_engine.py
```

فعلاً بدون migration؛ evidence داخل `raw_candidate` ذخیره شود.

### 6.3 ساختار پیشنهادی evidence

```json
{
  "rule": "semantic_wattage_mismatch",
  "reason_code": "semantic_wattage_mismatch",
  "severity": "blocker",
  "confidence": "high",
  "source": {
    "value": 1500,
    "source": "title",
    "evidence": "1500 وات"
  },
  "candidate": {
    "value": 2500,
    "source": "title",
    "evidence": "2500 وات"
  }
}
```

برای compatibility، `blocker_reasons` باید باقی بماند:

```python
comparison.blocker_reasons
comparison.evidence
comparison.details
```

### 6.4 Evidence برای prefilter

Candidate Quality Filter هم باید evidence بسازد:

```json
{
  "stage": "prefilter",
  "reason_code": "prefilter_not_cheaper",
  "confidence": "high",
  "source": {"price": 1000000},
  "candidate": {"price": 1200000}
}
```

### 6.5 آینده

بعداً اگر evidence خیلی مهم شد، مدل `AnalysisCandidate` می‌تواند فیلد `evidence_json` بگیرد. فعلاً نه.

### 6.6 نتیجه اجرای Task 2

پیاده‌سازی انجام‌شده:

- `SemanticComparison` اکنون فیلد `evidence` دارد.
- هر semantic blocker ساختار evidence شامل `rule`، `reason_code`، `severity`، `confidence`، `key` و values source/candidate می‌سازد.
- evidence برای compatibility در `comparison.details['evidence']` هم قرار می‌گیرد.
- `score_candidate(...)` evidence را داخل `raw_candidate.semantic_evidence` ذخیره می‌کند.
- تست evidence برای `semantic_wattage_mismatch` اضافه شد.

## 7. Task 3 — Category Catalog + Simple Family Router

**وضعیت: انجام شد.** فایل Excel به artifact پایدار داخل repo تبدیل شد و loader/router ساده اضافه شد.

### 7.1 هدف

از فایل `کتگوری ها.xlsx` یک catalog پایدار بسازیم و family اولیه محصول را با category-first routing تشخیص دهیم.

### 7.2 artifact داخل repo

فایل پیشنهادی:

```text
daily_off/data/category_catalog.json
```

ساختار هر row:

```json
{
  "cat_lvl1_title": "مواد غذایی",
  "cat_lvl1_id": 1,
  "cat_lvl2_title": "آجیل و خشکبار",
  "cat_lvl2_id": 13,
  "cat_lvl3_title": "بادام درختی",
  "cat_lvl3_id": 115,
  "cat_leaf_title": "بادام درختی"
}
```

### 7.3 فایل loader/router پیشنهادی

```text
daily_off/category_catalog.py
```

یا اگر ساختار بهتر خواستیم:

```text
daily_off/matching/category_catalog.py
daily_off/matching/family_router.py
```

برای فاز اول ساده‌تر:

```text
daily_off/category_catalog.py
daily_off/family_router.py
```

### 7.4 Familyهای اولیه

شروع با familyهای محدود:

```python
LEVEL1_TO_FAMILY = {
    "کالای دیجیتال": "digital",
    "مواد غذایی": "food",
    "مد و پوشاک": "fashion",
    "آرایشی و بهداشتی": "beauty_health",
    "فرهنگی، آموزشی و سرگرمی": "culture_entertainment",
    "ورزش و سفر": "sport_travel",
    "سلامت، درمان و طب": "health_medical",
    "صنایع دستی": "handicraft",
    "طلا و نقره": "jewelry",
    "خانه و آشپزخانه": "home_living",
    "ابزارآلات و تجهیزات خودرو": "tools_auto",
}
```

Overrideهای level2 مهم:

```python
LEVEL2_TO_FAMILY = {
    "لوازم یدکی خودرو": "auto_part",
    "لوازم جانبی خودرو": "auto_part",
    "ابزار برقی": "tools",
    "ابزار دستی": "tools",
    "لوازم برقی": "home_appliance",
    "گوشی موبایل": "digital",
}
```

اگر category unknown یا `سایر` بود:

```text
family = generic
confidence = low
```

### 7.5 تابع پیشنهادی

```python
def resolve_category_path(category_title='', navigation_title='', navigation_slug=''):
    ...


def route_family(category_path, title='', attributes_text=''):
    return {
        "family": "food",
        "confidence": "high",
        "signals": ["category_leaf", "level1"],
        "category_path": {...}
    }
```

### 7.6 اولویت routing

```text
Category first
Title cues fallback
Attributes support
```

اما با category confidence:

- category leaf exact match → high
- level2/lvl1 match → medium/high
- generic/sayer/unknown → low و title cues حق دخالت بیشتر دارد

### 7.7 نتیجه اجرای Task 3

پیاده‌سازی انجام‌شده:

- `daily_off/data/category_catalog.json` با ۹۴۱ row از `C:\Users\iliaco\Downloads\کتگوری ها.xlsx` ساخته شد.
- `daily_off/category_catalog.py` برای load و resolve کردن category path اضافه شد.
- `daily_off/family_router.py` برای route کردن family با اولویت category و fallback سبک title cues اضافه شد.
- تست‌های family routing برای `گوشی موبایل`، `لنت ترمز خودرو`، `لوازم برقی/کولر آبی`، `بادام درختی` و unknown اضافه شد.

## 8. Task 4 — استفاده محدود از family در موتور

**وضعیت: انجام شد.** استفاده family محدود و کم‌ریسک نگه داشته شد.

در فاز اول family نباید همه چیز را تغییر دهد.

استفاده‌های کم‌ریسک:

1. ذخیره family routing در `raw_candidate` برای debug.
2. استفاده از family برای فعال/غیرفعال کردن ruleهای خاص:
   - fish/honey/nut فقط در food یا وقتی title cue واضح دارد.
   - wattage/brand strictness در tools/digital/home_appliance بیشتر شود.
3. استفاده در Candidate Quality Filter برای category mismatch آینده.

### 8.1 نتیجه اجرای Task 4

پیاده‌سازی انجام‌شده:

- `score_candidate(...)` برای source و candidate خروجی `route_product_family(...)` می‌سازد.
- خروجی routing در `raw_candidate.family_routing` ذخیره می‌شود.
- strict semantic rules مربوط به برند، وات و مدل فقط برای familyهای فنی (`tools`, `digital`, `home_appliance`, `tools_auto`, `auto_part`) یا generic فعال می‌شوند.
- Category mismatch هنوز وارد prefilter نشده و برای آینده نگه داشته شده است.
- ProductIdentity کامل، family profileهای زیاد و migration جدید اضافه نشده‌اند.

## 9. چیزهایی که فعلاً انجام نمی‌دهیم

فعلاً انجام نشود:

- ProductIdentity کامل
- Family profileهای زیاد
- ۵۰ subfamily برای food/tools/fashion
- مدل ML جدید
- تغییر سنگین scoring formula
- migration جدید برای evidence
- وارد کردن free shipping یا customer satisfaction به scoring

## 10. تست و verification

### 10.1 تست‌های لازم

اضافه/آپدیت تست‌ها در:

```text
daily_off/tests.py
```

برای Candidate Filter:

- candidate گران‌تر با price معتبر → prefilter_not_cheaper
- candidate بدون price → حذف نشود
- title overlap صفر → prefilter_title_overlap_too_low
- candidate خوب → pass

برای Evidence:

- semantic_wattage_mismatch evidence source/candidate value داشته باشد.
- semantic_brand_mismatch evidence برندها را ذخیره کند.

برای Family Router:

- `گوشی موبایل` با lvl3 خالی → `digital`, confidence high
- `لنت ترمز خودرو` → `auto_part`
- `کولر آبی` → `home_appliance`
- `آجیل و خشکبار` / `بادام درختی` → `food`
- unknown → `generic`, confidence low

### 10.2 دستورات verification

```powershell
& "D:\basalam\salam_offer\.venv\Scripts\python.exe" "D:\basalam\salam_offer\manage.py" test daily_off.tests
& "D:\basalam\salam_offer\.venv\Scripts\python.exe" "D:\basalam\salam_offer\manage.py" check
```

### 10.3 verification با دیتاست دستی

فایل دیتاست دستی:

```text
C:\Users\iliaco\Downloads\دیتاست 1_files\sheet001.htm
```

بعد از تغییرات، یک اسکریپت محلی read-only اجرا شود که:

- ردیف‌ها را parse کند.
- source/candidate titleها را به semantic/family/prefilter بدهد.
- نشان دهد کدام false positiveها blocker/prefilter گرفته‌اند.

## 11. معیار موفقیت فاز بعدی

فاز بعدی موفق است اگر:

1. Candidateهای گران‌تر واضح قبل از detail fetch حذف شوند. ✅
2. Candidateهای بی‌ربط با title overlap صفر حذف شوند. ✅
3. Semantic blockerها evidence ساختاریافته داشته باشند. ✅
4. فایل category catalog داخل repo وجود داشته باشد و runtime به Downloads وابسته نباشد. ✅
5. route_family برای categoryهای اصلی درست کار کند. ✅
6. تست‌ها pass شوند. ✅
7. `PROJECT_HANDOFF.md` با تغییرات جدید آپدیت شود. ✅
8. تغییرات روی `origin/salam-test` commit و push شوند. ⏸ طبق درخواست جدید کاربر فعلاً push انجام نمی‌شود تا دستور صریح بدهد.

## 12. فایل‌های اصلی فاز بعدی

احتمالاً تغییر خواهند کرد:

```text
daily_off/analysis_engine.py
daily_off/semantic_rules.py
daily_off/tests.py
PROJECT_HANDOFF.md
```

احتمالاً اضافه خواهند شد:

```text
daily_off/data/category_catalog.json
daily_off/category_catalog.py
daily_off/family_router.py
```

اگر ساختار package لازم شد:

```text
daily_off/matching/__init__.py
daily_off/matching/category_catalog.py
daily_off/matching/family_router.py
```

ولی برای فاز بعدی، ساده‌تر نگه داشتن ساختار بهتر است.

## 13. تصمیم‌های قطعی تا این لحظه

- سطح دسترسی/OAuth اولویت ۲ است و فعلاً وارد این فاز نمی‌شود.
- تمرکز فعلی روی تقویت منطق موتور تحلیل است.
- ProductIdentity کامل فعلاً انجام نمی‌شود.
- Candidate Quality Filter و Evidence System اولویت اصلی هستند.
- Category Catalog / Family Router با فایل `کتگوری ها.xlsx` باید وارد repo شود.
- همه تغییرات کامل و verified باید بدون prompt جداگانه commit و push شوند.
