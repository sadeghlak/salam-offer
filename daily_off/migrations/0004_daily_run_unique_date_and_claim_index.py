from django.db import migrations, models
from django.db.models import Count


TERMINAL_ANALYSIS_STATUSES = {'analyzed', 'no_match', 'analysis_error'}


def snapshot_score(snapshot):
    terminal = 1 if snapshot.analysis_status in TERMINAL_ANALYSIS_STATUSES else 0
    fetched = 1 if snapshot.fetch_status == 'details_fetched' else 0
    has_result = 1 if snapshot.product_url1 or snapshot.product_url2 or snapshot.product_url3 or snapshot.accepted_candidates_count else 0
    updated_at = snapshot.updated_at or snapshot.created_at
    return terminal, fetched, has_result, updated_at, snapshot.id


def copy_snapshot_fields(source, target):
    skip = {'id', 'run', 'created_at'}
    for field in source._meta.concrete_fields:
        if field.name in skip:
            continue
        setattr(target, field.name, getattr(source, field.name))
    target.run = target.run
    target.save()


def merge_duplicate_daily_runs(apps, schema_editor):
    DailyRun = apps.get_model('daily_off', 'DailyRun')
    DailyProductSnapshot = apps.get_model('daily_off', 'DailyProductSnapshot')

    duplicate_dates = (
        DailyRun.objects.values('business_date')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('business_date', flat=True)
    )

    for business_date in duplicate_dates:
        runs = list(DailyRun.objects.filter(business_date=business_date).order_by('created_at', 'id'))
        if not runs:
            continue

        canonical = runs[0]
        merged_config = canonical.config_json.copy() if isinstance(canonical.config_json, dict) else {}
        notes = [canonical.notes] if canonical.notes else []
        max_input_count = canonical.input_count or 0

        for duplicate in runs[1:]:
            if isinstance(duplicate.config_json, dict):
                merged_config.update(duplicate.config_json)
            if duplicate.notes:
                notes.append(duplicate.notes)
            max_input_count = max(max_input_count, duplicate.input_count or 0)

            snapshots = list(DailyProductSnapshot.objects.filter(run=duplicate).order_by('id'))
            for snapshot in snapshots:
                existing = DailyProductSnapshot.objects.filter(
                    run=canonical,
                    source_product_id=snapshot.source_product_id,
                ).first()

                if existing is None:
                    snapshot.run = canonical
                    snapshot.business_date = canonical.business_date
                    snapshot.save(update_fields=['run', 'business_date', 'updated_at'])
                    continue

                if snapshot_score(snapshot) > snapshot_score(existing):
                    copy_snapshot_fields(snapshot, existing)
                    existing.run = canonical
                    existing.business_date = canonical.business_date
                    existing.save(update_fields=[field.name for field in existing._meta.concrete_fields if field.name not in {'id', 'created_at'}])
                snapshot.delete()

            duplicate.delete()

        canonical.input_count = max_input_count
        canonical.config_json = merged_config
        canonical.notes = '\n'.join([note for note in notes if note])
        canonical.fetched_count = canonical.snapshots.filter(fetch_status='details_fetched').count()
        canonical.error_count = canonical.snapshots.filter(fetch_status='fetch_error').count()
        canonical.save()


class Migration(migrations.Migration):

    dependencies = [
        ('daily_off', '0003_dailyproductsnapshot_accepted_candidates_count_and_more'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_daily_runs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='dailyrun',
            constraint=models.UniqueConstraint(fields=['business_date'], name='uniq_daily_run_business_date'),
        ),
        migrations.AddIndex(
            model_name='dailyproductsnapshot',
            index=models.Index(fields=['analysis_status', 'fetch_status', 'business_date', 'id'], name='dps_claim_idx'),
        ),
    ]
