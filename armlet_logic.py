import time
import logging
from typing import Any
from config import Settings

logger = logging.getLogger(__name__)

ARMLET_ITEM_NAME = "item_armlet"
ARMLET_HP_BONUS = 550
BONUS_TOLERANCE = 150
CONFIRM_TIMEOUT_SECONDS = 0.8
CONFIRM_RETRY_SECONDS = 0.35
EXTERNAL_GRACE_SECONDS = 1.0
EXTERNAL_GRACE_SECONDS_CRITICAL = 0.15
_armlet_active: bool = False
_last_health: int | None = None
_passive_anchor: int | None = None
_passive_last_seen: int | None = None
_last_action_time: float | None = None

_pending_confirm: bool = False
_pre_action_max_health: int = 0
_external_grace_until: float = 0.0
_combo_mode: bool = False


def _reset_state() -> None:
    global _armlet_active, _last_health, _passive_anchor, _passive_last_seen, _last_action_time
    global _pending_confirm, _pre_action_max_health, _external_grace_until, _combo_mode
    _armlet_active = False
    _last_health = None
    _passive_anchor = None
    _passive_last_seen = None
    _last_action_time = None
    _pending_confirm = False
    _pre_action_max_health = 0
    _external_grace_until = 0.0
    _combo_mode = False


def should_toggle_armlet(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    global _armlet_active, _last_health, _passive_anchor, _passive_last_seen, _last_action_time
    global _pending_confirm, _pre_action_max_health, _external_grace_until, _combo_mode

    hero_data = _extract_hero(payload)
    items_data = _extract_items(payload)

    health = hero_data.get("health", 0)
    max_health = hero_data.get("max_health", 1)
    if max_health <= 0:
        max_health = 1

    delta_hp = (health - _last_health) if _last_health is not None else 0
    _last_health = health

    armlet_info = _find_armlet(items_data)
    if armlet_info is None:
        _reset_state()
        return _result("none", health, max_health, "not_found")

    if health <= 0:
        _reset_state()
        return _result("none", health, max_health, "dead")

    now = time.monotonic()
    hp_threshold = settings.threshold_hp(max_health)

    # --- Seed inicial: primer tick que vemos el item, sin asumir estado ---
    if _passive_anchor is None:
        _passive_anchor = max_health
        _passive_last_seen = max_health
        logger.info("Armlet detectado, seed inicial (max_hp=%d). Estado asumido: inactivo.", max_health)
        return _result("none", health, max_health, "seeding", armlet_status="inactive")

    # --- Resolver confirmación de nuestra última acción, si hay una pendiente ---
    if _pending_confirm:
        delta_mh = max_health - _pre_action_max_health
        if delta_mh >= (ARMLET_HP_BONUS - BONUS_TOLERANCE):
            _armlet_active = True
            _pending_confirm = False
            logger.info("Acción confirmada: ON (delta_max_hp=+%d)", delta_mh)
        elif delta_mh <= -(ARMLET_HP_BONUS - BONUS_TOLERANCE):
            _armlet_active = False
            _pending_confirm = False
            logger.info("Acción confirmada: OFF (delta_max_hp=%d)", delta_mh)
        else:
            elapsed = now - _last_action_time
            if elapsed >= CONFIRM_TIMEOUT_SECONDS:
                logger.warning(
                    "Sin confirmación tras %.1fs (delta_max_hp=%d) — el press probablemente falló. "
                    "Mantengo estado previo: %s",
                    CONFIRM_TIMEOUT_SECONDS, delta_mh, _armlet_active,
                )
                _pending_confirm = False
            elif elapsed >= CONFIRM_RETRY_SECONDS and delta_mh == 0:
                # Un tick completo pasó y el delta sigue en cero: el press no llegó.
                # Re-enviamos inmediatamente sin esperar el timeout completo.
                logger.warning(
                    "Delta cero tras %.2fs — reintentando press (intento rápido)",
                    elapsed,
                )
                _last_action_time = now
                _passive_anchor = max_health
                _passive_last_seen = max_health
                return _result(
                    "activate" if not _armlet_active else "deactivate",
                    health, max_health, "confirm_retry",
                    armlet_status=("active" if _armlet_active else "inactive"),
                )
            else:
                logger.debug(
                    "Esperando confirmación (%.2fs transcurridos, delta_max_hp=%d)",
                    elapsed, delta_mh,
                )
        _passive_anchor = max_health
        _passive_last_seen = max_health
        return _result("none", health, max_health, "confirming_toggle", armlet_status=("active" if _armlet_active else "inactive"))

    # --- Detección pasiva: toggle externo fuera de nuestras acciones ---
    delta_from_anchor = max_health - _passive_anchor

    if abs(delta_from_anchor) >= (ARMLET_HP_BONUS - BONUS_TOLERANCE):
        if delta_from_anchor > 0 and not _armlet_active:
            _armlet_active = True
            _external_grace_until = now + EXTERNAL_GRACE_SECONDS
            _combo_mode = False  # toggle externo interrumpe cualquier combo
            logger.info("Activación externa detectada (delta acumulado=+%d)", delta_from_anchor)
            _passive_anchor = max_health
        elif delta_from_anchor < 0 and _armlet_active:
            _armlet_active = False
            _combo_mode = False  # toggle externo interrumpe cualquier combo
            _armlet_active = False
            # Si HP ya está bajo el threshold, grace period corto — no tiene sentido
            # esperar 1s mientras el jugador agoniza
            if health < hp_threshold:
                grace = EXTERNAL_GRACE_SECONDS_CRITICAL
                logger.info(
                    "Desactivación externa con HP crítico (HP %d/%d) — grace corto (%.2fs)",
                    health, max_health, grace,
                )
            else:
                grace = EXTERNAL_GRACE_SECONDS
            _external_grace_until = now + grace
            logger.info("Desactivación externa detectada (delta acumulado=%d)", delta_from_anchor)
            _passive_anchor = max_health
        else:
            _passive_anchor = max_health
    elif max_health == _passive_last_seen:
        _passive_anchor = max_health
        _passive_last_seen = max_health

    _passive_last_seen = max_health

    # --- Período de gracia: el jugador está microeando manualmente ---
    # Excepción: HP bajo threshold tiene prioridad sobre el grace period
    in_panic = health < hp_threshold
    if now < _external_grace_until and not in_panic:
        return _result(
            "none", health, max_health, "external_grace",
            armlet_status=("active" if _armlet_active else "inactive"),
        )

    # --- Debounce: reemplaza al cooldown del GSI ---
    can_act = _last_action_time is None or (now - _last_action_time) >= settings.toggle_min_interval

    # --- Panic combo: armlet toggle trick para HP bajo con armlet ya activo ---
    # Si el armlet está ON y HP cae bajo el threshold, hacemos off+on rápido
    # para resetear el bonus de HP (armlet toggle trick)
    taking_massive_damage = delta_hp < -int(max_health * settings.combat_delta_pct)

    # Caso 1: armlet ON, HP bajo threshold → iniciar combo apagando
    if _armlet_active and health < hp_threshold and can_act:
        _pending_confirm = True
        _combo_mode = True
        _pre_action_max_health = max_health
        _last_action_time = now
        logger.info("PANIC COMBO: desactivando armlet (HP %d/%d = %.1f%%)", health, max_health, health/max_health*100)
        return _result("deactivate", health, max_health, "panic_combo_off", armlet_status="active")

    # Caso 2: combo en curso, armlet OFF, HP bajo threshold → completar combo activando
    if _combo_mode and not _armlet_active and health < hp_threshold:
        _pending_confirm = True
        _combo_mode = False
        _pre_action_max_health = max_health
        _last_action_time = now
        logger.info("PANIC COMBO: reactivando armlet (HP %d/%d)", health, max_health)
        return _result("activate", health, max_health, "panic_combo_on", armlet_status="inactive")

    # Cancelar combo si HP subió por encima del threshold
    if _combo_mode and health >= hp_threshold:
        logger.info("PANIC COMBO: cancelado, HP recuperado (%d/%d)", health, max_health)
        _combo_mode = False

    # --- Decisión ---
    if _armlet_active:
        deactivate_hp = int(max_health * settings.deactivate_threshold_pct)
        taking_damage = delta_hp < -int(max_health * settings.combat_delta_pct)
        if health >= deactivate_hp and not taking_damage and can_act:
            _pending_confirm = True
            _pre_action_max_health = max_health
            _last_action_time = now
            logger.info("Desactivación (HP %d/%d recuperado)", health, max_health)
            return _result("deactivate", health, max_health, "hp_recovered", armlet_status="active")
        return _result("none", health, max_health, "keeping_active", armlet_status="active")

    if health < hp_threshold:
        if can_act:
            _pending_confirm = True
            _pre_action_max_health = max_health
            _last_action_time = now
            logger.info("Activación (HP %d/%d)", health, max_health)
            return _result("activate", health, max_health, "low_hp")
        return _result("none", health, max_health, "debounced", armlet_status="cooldown")

    return _result("none", health, max_health, "hp_above_threshold")


def _result(
    action: str,
    health: int,
    max_health: int,
    reason: str,
    armlet_status: str = "inactive",
) -> dict[str, Any]:
    pct = (health / max_health * 100) if max_health > 0 else 0.0
    return {
        "action": action,
        "health": health,
        "max_health": max_health,
        "hp_percent": round(pct, 1),
        "armlet_status": armlet_status,
        "reason": reason,
    }


def _extract_hero(payload: dict[str, Any]) -> dict[str, Any]:
    hero = payload.get("hero")
    if isinstance(hero, dict):
        team_keys = [k for k in hero if k.startswith("team")]
        if team_keys:
            first_team = hero.get(team_keys[0], {})
            player_keys = [k for k in first_team if k.startswith("player")]
            if player_keys:
                result = first_team.get(player_keys[0], {})
                logger.debug("extract_hero: team/player, health=%s", result.get("health"))
                return result
            logger.debug("extract_hero: team but no player keys")
        logger.debug("extract_hero: flat, health=%s", hero.get("health"))
        return hero
    logger.debug("extract_hero: none (type: %s)", type(hero).__name__ if hero is not None else "None")
    return {}


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if isinstance(items, dict):
        team_keys = [k for k in items if k.startswith("team")]
        if team_keys:
            first_team = items.get(team_keys[0], {})
            player_keys = [k for k in first_team if k.startswith("player")]
            if player_keys:
                slots = first_team.get(player_keys[0], {})
                result = _parse_slot_items(slots)
                logger.debug("extract_items: team/player, %d items", len(result))
                return result
            logger.debug("extract_items: team but no player keys")
        slot_keys = [k for k in items if k.startswith("slot")]
        if slot_keys:
            result = _parse_slot_items(items)
            logger.debug("extract_items: slots, %d items", len(result))
            return result
        logger.debug("extract_items: unknown keys: %s", list(items.keys())[:10])
        return []
    if isinstance(items, list):
        result = _normalize_items(items)
        logger.debug("extract_items: list, %d items", len(result))
        return result

    hero_items = payload.get("hero", {}).get("items")
    if isinstance(hero_items, list):
        result = _normalize_items(hero_items)
        logger.debug("extract_items: hero.items, %d items", len(result))
        return result

    logger.debug("extract_items: none (type: %s)", type(items).__name__ if items is not None else "None")
    return []


def _parse_slot_items(slots: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for slot_key in sorted(slots.keys()):
        slot_data = slots[slot_key]
        if isinstance(slot_data, dict) and slot_data.get("name", "") != "empty":
            result.append({
                "item_name": slot_data.get("name", ""),
                "cooldown": slot_data.get("cooldown", 0),
            })
    return result


def _normalize_items(items: list[Any]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("item_name") or item.get("name", "")
            result.append({
                "item_name": name,
                "cooldown": item.get("cooldown", 0),
            })
    return result


def _find_armlet(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("item_name") == ARMLET_ITEM_NAME:
            return item
    return None
