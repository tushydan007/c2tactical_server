import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Periodic tasks configuration
app.conf.beat_schedule = {
    "cleanup-old-analyses": {
        "task": "satellite.tasks.cleanup_old_analyses",
        "schedule": crontab(hour=2, minute=0),  # Run daily at 2 AM
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
