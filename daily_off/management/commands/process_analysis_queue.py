import logging
import signal
import time

from django.core.management.base import BaseCommand

from daily_off.services import process_analysis_batch


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending Salam Offer product analysis jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Keep polling the queue until the process is stopped.')
        parser.add_argument('--sleep', type=float, default=2.0, help='Seconds to sleep between empty loop iterations.')
        parser.add_argument('--limit', type=int, default=1, help='Number of products to process per batch.')
        parser.add_argument('--run-key', default='', help='Optional run key to restrict processing to one daily run.')
        parser.add_argument('--today-only', action='store_true', help='Only process pending analysis for today when no run key is provided.')
        parser.add_argument('--older-than-minutes', type=int, default=30, help='Requeue running jobs older than this many minutes.')
        parser.add_argument('--actor', default='analysis_worker', help='Actor name stored in analysis logs.')

    def handle(self, *args, **options):
        keep_running = options['loop']
        sleep_seconds = max(0.5, float(options['sleep']))
        limit = max(1, min(int(options['limit']), 10))
        run_key = options['run_key'] or None
        all_dates = not options['today_only'] and not run_key
        older_than_minutes = int(options['older_than_minutes'])
        actor = options['actor']
        should_stop = False

        def request_stop(signum, frame):
            nonlocal should_stop
            should_stop = True
            self.stdout.write(self.style.WARNING('Stop signal received; worker will stop after current batch.'))

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

        self.stdout.write(self.style.SUCCESS(
            f'Analysis worker started loop={keep_running} limit={limit} sleep={sleep_seconds}s run_key={run_key or "*"} all_dates={all_dates}'
        ))

        while True:
            result = process_analysis_batch(
                run_key=run_key,
                limit=limit,
                older_than_minutes=older_than_minutes,
                all_dates=all_dates,
                actor=actor,
            )
            self.stdout.write(
                'processed={processed_count} success={success_count} errors={retry_count} pending={pending_count} requeued={requeued_stale_count}'.format(**result)
            )
            logger.info('analysis worker batch result %s', result)

            if should_stop or not keep_running:
                break
            if result['processed_count'] == 0:
                time.sleep(sleep_seconds)

        self.stdout.write(self.style.SUCCESS('Analysis worker stopped.'))
