from django import template

register = template.Library()


JALALI_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
]


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30

    return jy, jm, jd


@register.filter
def jalali_date(value):
    if not value:
        return '-'
    if hasattr(value, 'date'):
        value = value.date()
    try:
        jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
    except AttributeError:
        return value
    return f'{jd} {JALALI_MONTHS[jm - 1]} {jy}'


@register.filter
def toman(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        value = 0
    if not value:
        return '-'
    return f'{value:,}'


@register.filter
def status_label(value):
    labels = {
        'pending': 'در انتظار',
        'running': 'در حال اجرا',
        'completed': 'کامل شده',
        'partial_failed': 'بخشی ناموفق',
        'failed': 'ناموفق',
        'analysis_pending': 'در انتظار تحلیل',
        'analysis_running': 'در حال تحلیل',
        'analyzed': 'تحلیل شده',
        'no_match': 'بدون نتیجه',
        'analysis_error': 'خطای تحلیل',
        'details_fetched': 'جزئیات دریافت شد',
        'fetch_error': 'خطای دریافت جزئیات',
    }
    return labels.get(value, value or '-')
