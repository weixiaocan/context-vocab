from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.models import ReviewAnswerRequest
from app.services import deck

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request, rebuild: bool = False) -> HTMLResponse:
    today = date.today()
    cards = (
        deck.rebuild_daily_deck(request.app.state.db, request.app.state.settings, today)
        if rebuild
        else deck.get_or_create_daily_deck(request.app.state.db, request.app.state.settings, today)
    )
    backlog = deck.backlog_count(request.app.state.db)
    pending_enrichment = deck.pending_enrichment_count(request.app.state.db)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "cards": cards,
            "cards_json": json.dumps(cards, ensure_ascii=False),
            "backlog": backlog,
            "pending_enrichment": pending_enrichment,
            "today": today.isoformat(),
        },
    )


@router.post("/review/answer")
def answer(payload: ReviewAnswerRequest, request: Request) -> dict[str, object]:
    try:
        return deck.answer_card(request.app.state.db, date.today(), payload.word, payload.correct)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
