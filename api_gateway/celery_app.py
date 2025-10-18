from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from celery import Celery
from celery.schedules import crontab

from api_gateway.config import get_settings
from api_gateway.database.db import get_database
from api_gateway.services.content.factory import get_content_provider
from api_gateway.services.email.factory import get_email_provider
from api_gateway.services.tokens.email_toggle_tokens import create_opt_out_token

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger("celery.weekly_digest")


def _templates_env() -> Environment:
    # api_gateway/services/email/templates
    here = os.path.dirname(__file__)
    templates_dir = os.path.join(here, "services", "email", "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )
    return env


def _build_public_url(path: str, query: dict[str, str]) -> str:
    base = get_settings().HOST_URL.rstrip('/')
    from urllib.parse import urlencode
    return f"{base}{path}?{urlencode(query)}"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(s: str) -> datetime:
    # Python 3.11+ supports fromisoformat with offset
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _default_week_window(now_utc: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now_utc = now_utc or datetime.now(timezone.utc)
    start = now_utc - timedelta(days=7)
    return (start, now_utc)


settings = get_settings()

broker_url = settings.REDIS_URL
result_backend = settings.REDIS_URL

app = Celery(
    "api_gateway",
    broker=broker_url,
    backend=result_backend,
)

# JSON serializer only; pass ISO strings for datetimes
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
)

# Eager mode for tests if desired
task_always_eager_env = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() in {"1", "true", "yes"}
if task_always_eager_env or (getattr(settings, "ENVIRONMENT", "").lower() == "test"):
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True


@app.task(bind=True, autoretry_for=(RuntimeError,), retry_backoff=30, retry_jitter=True, retry_kwargs={"max_retries": 3})
def build_and_send_weekly_digest(self, user_id: str, week_start_iso: Optional[str] = None, week_end_iso: Optional[str] = None) -> dict:
    """Build content from ContentProvider and send via EmailProvider.

    Retries on RuntimeError (e.g., provider failures). Returns a summary dict.
    """
    try:
        week_start, week_end = (_default_week_window()) if not week_start_iso or not week_end_iso else (_parse_iso(week_start_iso), _parse_iso(week_end_iso))

        db = get_database()
        user = db.users.find_one({"id": user_id}) or {}
        email = user.get("email")
        role = user.get("role")
        if not email or role != "individual":
            logger.info("digest_skip_non_individual_or_no_email", extra={"user_id": user_id})
            return {"ok": False, "reason": "no_email_or_not_individual"}

        content_provider = get_content_provider()
        payload = content_provider.get_weekly_content(user_id=user_id, week_start=week_start, week_end=week_end)

        # Build unsubscribe
        token = create_opt_out_token(user_id)
        unsubscribe_url = _build_public_url("/public/email-digest/opt-out", {"token": token})

        # Render templates
        env = _templates_env()
        html_tpl = env.get_template("weekly_digest.html")
        html = html_tpl.render(
            title=payload.title,
            intro=payload.intro,
            metrics=payload.metrics,
            agents_used=payload.agents_used,
            latest_conversation=payload.latest_conversation,
            unsubscribe_url=unsubscribe_url,
        )
        # Optional text template (not strictly required by many providers)
        try:
            txt_tpl = env.get_template("weekly_digest.txt")
            text = txt_tpl.render(
                title=payload.title,
                intro=payload.intro,
                metrics=payload.metrics,
                agents_used=payload.agents_used,
                latest_conversation=payload.latest_conversation,
                unsubscribe_url=unsubscribe_url,
            )
        except Exception:
            text = None

        provider = get_email_provider()
        subject = payload.title or "Your weekly summary"
        result = provider.send_email(to=email, subject=subject, html=html, text=text)
        if not result.ok:
            logger.warning(
                "digest_send_failed",
                extra={
                    "task_id": getattr(self.request, 'id', None),
                    "user_id": user_id,
                    "email": email,
                    "provider": getattr(result, 'provider', None),
                    "message_id": getattr(result, 'message_id', None),
                    "error": result.error,
                },
            )
            raise RuntimeError(result.error or "provider_send_failed")

        logger.info("digest_sent", extra={
            "task_id": getattr(self.request, 'id', None),
            "user_id": user_id,
            "email": email,
            "week_start": _iso(week_start),
            "week_end": _iso(week_end),
            "message_id": result.message_id,
            "provider": result.provider,
        })
        return {
            "ok": True,
            "user_id": user_id,
            "email": email,
            "week_start": _iso(week_start),
            "week_end": _iso(week_end),
            "message_id": result.message_id,
        }
    except Exception as e:
        logger.exception("digest_task_exception", extra={"user_id": user_id})
        raise


@app.task(bind=True)
def orchestrate_weekly_digest_batch(self, week_start_iso: Optional[str] = None, week_end_iso: Optional[str] = None) -> dict:
    """Find opted-in individuals and enqueue per-user digest tasks.

    If EMAIL_WEEKLY_ENABLED is False, acts as a no-op.
    """
    if not getattr(settings, "EMAIL_WEEKLY_ENABLED", False):
        logger.info("weekly_digest_disabled", extra={"task_id": getattr(self.request, 'id', None)})
        return {"enqueued": 0, "disabled": True}

    db = get_database()
    # Find all individuals with weekly_digest_enabled == True
    individuals = db.individuals.find({"weekly_digest_enabled": True}, {"id": 1})

    week_start: Optional[datetime]
    week_end: Optional[datetime]
    if week_start_iso and week_end_iso:
        week_start, week_end = _parse_iso(week_start_iso), _parse_iso(week_end_iso)
    else:
        week_start, week_end = _default_week_window()

    enqueued = 0
    for ind in individuals:
        individual_id = ind.get("id")
        if not individual_id:
            continue
        # Get the user doc associated with this individual
        user = db.users.find_one({"role": "individual", "role_entity_id": individual_id}) or {}
        user_id = user.get("id")
        if not user_id:
            continue
        # Enqueue task with ISO strings (JSON-serializable)
        build_and_send_weekly_digest.delay(user_id, _iso(week_start), _iso(week_end))
        enqueued += 1

    logger.info("weekly_digest_enqueued", extra={
        "task_id": getattr(self.request, 'id', None),
        "count": enqueued,
        "week_start": _iso(week_start),
        "week_end": _iso(week_end)
    })
    return {"enqueued": enqueued, "week_start": _iso(week_start), "week_end": _iso(week_end)}


# -----------------------------
# Beat Schedule (Weekly)
# -----------------------------
if getattr(settings, "EMAIL_WEEKLY_ENABLED", False):
    try:
        dow = int(getattr(settings, "WEEKLY_DIGEST_DAY_UTC", 1))  # 0=Mon
        hour = int(getattr(settings, "WEEKLY_DIGEST_HOUR_UTC", 9))
        app.conf.beat_schedule = {
            "weekly-digest-batch": {
                "task": "api_gateway.celery_app.orchestrate_weekly_digest_batch",
                "schedule": crontab(day_of_week=dow, hour=hour, minute=0),
                "args": (),
            }
        }
        logger.info("celery_beat_configured", extra={"day_of_week": dow, "hour": hour})
    except Exception as e:
        logger.warning("celery_beat_schedule_setup_failed", extra={"error": str(e)})
else:
    # No schedule when feature flag is off
    app.conf.beat_schedule = {}
