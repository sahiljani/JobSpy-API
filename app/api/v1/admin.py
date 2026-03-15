from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import bad_request, unauthorized
from app.db.session import get_db
from app.schemas.admin import WebhookDlqItem, WebhookDlqResponse
from app.services.webhook_service import WebhookService

router = APIRouter(prefix='/v1/admin', tags=['admin'])


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise unauthorized('invalid API key')


@router.get('/webhooks/dlq', response_model=WebhookDlqResponse, dependencies=[Depends(_require_api_key)])
def list_webhook_dlq(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> WebhookDlqResponse:
    service = WebhookService(db)
    rows = service.list_dlq(limit=limit)
    return WebhookDlqResponse(
        items=[
            WebhookDlqItem(
                event_id=r.event_id,
                job_id=r.job_id,
                attempt=r.attempt,
                status_code=r.status_code,
                response_excerpt=r.response_excerpt,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.post('/webhooks/replay/{event_id}', dependencies=[Depends(_require_api_key)])
def replay_webhook_event(event_id: str, db: Session = Depends(get_db)) -> dict:
    service = WebhookService(db)
    try:
        ok = service.replay_event(event_id=event_id)
    except ValueError as exc:
        raise bad_request(str(exc), code='replay_error') from exc

    db.commit()
    return {'ok': ok, 'event_id': event_id}
