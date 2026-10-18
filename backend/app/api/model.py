"""Model card and dev-only admin endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.ml.train import ARTIFACTS
from app.schemas import ModelCardResponse

router = APIRouter()


@router.get("/card", response_model=ModelCardResponse)
def model_card() -> ModelCardResponse:
    """Return metrics, slices and the rendered model card markdown."""
    metrics_path = ARTIFACTS / "metrics.json"
    slices_path = ARTIFACTS / "slices.json"
    card_path = ARTIFACTS / "model_card.md"
    if not metrics_path.exists():
        raise HTTPException(
            status_code=503,
            detail={"code": "not_trained", "message": "Model artifacts are missing. Run `make train && make eval`."},
        )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    slices = json.loads(slices_path.read_text(encoding="utf-8")) if slices_path.exists() else {}
    card = card_path.read_text(encoding="utf-8") if card_path.exists() else ""
    return ModelCardResponse(metrics=metrics, slices=slices, card_markdown=card)


@router.post("/admin/reseed")
def reseed(seed: int = 42) -> dict[str, str]:
    """Re-run seed, train and scoring. Dev only, behind a config flag."""
    if not settings.enable_admin_reseed:
        raise HTTPException(
            status_code=403,
            detail={"code": "disabled", "message": "Admin reseed is disabled. Set ENABLE_ADMIN_RESEED=true to enable."},
        )
    from app.ml.scoring import score_open_cycle
    from app.ml.synth import write_db

    db_path = str(engine.url.database)
    write_db(db_path, seed)
    from app.db import init_db

    init_db()
    from app.ml import train as train_mod

    train_mod.main()
    with Session(engine) as session:
        n = score_open_cycle(session)
    return {"status": "ok", "message": f"Reseeded and scored {n} leases."}
