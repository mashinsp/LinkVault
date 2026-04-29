from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from messaging import publish_click_event

from cache import (
    get_cached_link,
    increment_click_count,
    invalidate_link,
    set_cached_link,
)
from config import settings
from core.errors import LinkExpired, LinkInactive, LinkNotFound, ShortcodeConflict
from core.shortcode import generate_shortcode
from database import get_db
from models.link import Link
from schemas.link import LinkCreate, LinkResponse, LinkStats

import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

MAX_SHORTCODE_RETRIES = 5


@router.post("/links", response_model=LinkResponse, status_code=201)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def create_link(request: Request, payload: LinkCreate, db: Session = Depends(get_db)):
    shortcode = payload.custom_shortcode or generate_shortcode()

    for attempt in range(MAX_SHORTCODE_RETRIES):
        try:
            link = Link(
                shortcode=shortcode,
                original_url=str(payload.url),
                expires_at=payload.expires_at,
            )
            db.add(link)
            db.commit()
            db.refresh(link)
            break
        except IntegrityError:
            db.rollback()
            if payload.custom_shortcode:
                raise ShortcodeConflict(shortcode)
            if attempt == MAX_SHORTCODE_RETRIES - 1:
                raise
            shortcode = generate_shortcode()

    return _to_response(link)


@router.get("/links/{shortcode}/stats", response_model=LinkStats)
async def get_link_stats(shortcode: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.shortcode == shortcode).first()
    if not link:
        raise LinkNotFound(shortcode)
    return link


@router.delete("/links/{shortcode}", status_code=204)
async def deactivate_link(shortcode: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.shortcode == shortcode).first()
    if not link:
        raise LinkNotFound(shortcode)
    link.is_active = False
    db.commit()
    await invalidate_link(shortcode)  # ← cache invalidation

@router.get("/{shortcode}")
@limiter.limit("120/minute")
async def redirect_link(
    request: Request,
    shortcode: str,
    user_agent: str | None = Header(None),
    db: Session = Depends(get_db),
):
    with tracer.start_as_current_span("redirect") as span:
        span.set_attribute("shortcode", shortcode)

        cached = await get_cached_link(shortcode)

        if cached:
            span.set_attribute("cache.hit", True)
            logger.info(
                "Cache hit on redirect",
                extra={"shortcode": shortcode, "event": "cache_hit"},
            )

            if not cached["is_active"]:
                span.set_attribute("redirect.result", "inactive")
                raise LinkInactive(shortcode)
            if cached["expires_at"] and datetime.fromisoformat(cached["expires_at"]) < datetime.now(timezone.utc):
                span.set_attribute("redirect.result", "expired")
                raise LinkExpired(shortcode)

            await publish_click_event(
                shortcode=shortcode,
                user_agent=user_agent,
                ip=request.client.host if request.client else None,
            )
            span.set_attribute("redirect.result", "success")
            return RedirectResponse(url=cached["original_url"], status_code=302)

        # Cache miss
        span.set_attribute("cache.hit", False)
        logger.info(
            "Cache miss on redirect",
            extra={"shortcode": shortcode, "event": "cache_miss"},
        )

        link = db.query(Link).filter(Link.shortcode == shortcode).first()

        if not link:
            span.set_attribute("redirect.result", "not_found")
            raise LinkNotFound(shortcode)
        if not link.is_active:
            span.set_attribute("redirect.result", "inactive")
            raise LinkInactive(shortcode)
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            span.set_attribute("redirect.result", "expired")
            raise LinkExpired(shortcode)

        await set_cached_link(shortcode, {
            "original_url": link.original_url,
            "is_active": link.is_active,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        })

        await publish_click_event(
            shortcode=shortcode,
            user_agent=user_agent,
            ip=request.client.host if request.client else None,
        )

        span.set_attribute("redirect.result", "success")
        return RedirectResponse(url=link.original_url, status_code=302)

def _to_response(link: Link) -> LinkResponse:
    return LinkResponse(
        id=link.id,
        shortcode=link.shortcode,
        original_url=link.original_url,
        short_url=f"{settings.base_url}/{link.shortcode}",
        click_count=link.click_count,
        is_active=link.is_active,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )