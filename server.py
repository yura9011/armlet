import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel

from armlet_logic import should_toggle_armlet
from config import Settings
from input_sim import InputSimulator

logger = logging.getLogger(__name__)


class ItemPayload(BaseModel):
    item_name: str = ""
    cooldown: int = 0


class HeroPayload(BaseModel):
    health: int = 0
    max_health: int = 0
    items: list[ItemPayload] = []


class GSIPayload(BaseModel):
    hero: Optional[HeroPayload] = None
    items: Optional[dict[str, Any]] = None
    abilities: Optional[dict[str, Any]] = None
    provider: Optional[dict[str, Any]] = None
    map: Optional[dict[str, Any]] = None
    player: Optional[dict[str, Any]] = None


def create_app(settings: Settings, simulator: InputSimulator) -> FastAPI:
    app = FastAPI(title="Auto-Armlet GSI")

    @app.post("/")
    async def gsi_endpoint(payload: GSIPayload, raw_request: Request) -> dict[str, Any]:
        raw_body: dict[str, Any] = {}
        try:
            raw_body = await raw_request.json()
        except Exception:
            logger.warning("Failed to parse raw JSON body")

        import json
        logger.info("RAW items: %s", json.dumps(raw_body.get("items", {}), default=str)[:500])
        logger.info("RAW hero items: %s", json.dumps(raw_body.get("hero", {}).get("items", {}), default=str)[:500])
        logger.info("RAW hero: %s", json.dumps(raw_body.get("hero", {}), default=str)[:300])

        result = should_toggle_armlet(raw_body, settings)

        if result["action"] in ("activate", "deactivate"):
            simulator.press_key(settings.key)

        action = result["action"]
        health = result["health"]
        max_hp = result["max_health"]
        pct = result["hp_percent"]
        armlet_st = result["armlet_status"]
        reason = result["reason"]
        logger.info(
            "action=%s hp=%d/%d (%.1f%%) armlet=%s reason=%s",
            action, health, max_hp, pct, armlet_st, reason,
        )

        return {"status": "ok", "action": action}

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app
