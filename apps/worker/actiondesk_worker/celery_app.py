from celery import Celery

from app.core.config import get_settings

celery_app = Celery("actiondesk", broker=get_settings().redis_url)
celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)


def noop() -> dict[str, str]:
    """Side-effect-free foundation probe; not a durable business job."""
    return {"status": "ok"}


celery_app.task(name="actiondesk.noop")(noop)
