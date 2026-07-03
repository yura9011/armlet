import time
import pytest

import armlet_logic
from armlet_logic import should_toggle_armlet, _reset_state
from config import Settings


@pytest.fixture(autouse=True)
def reset_state():
    _reset_state()
    armlet_logic.CONFIRM_TIMEOUT_SECONDS = 1.5
    armlet_logic.EXTERNAL_GRACE_SECONDS = 1.0
    yield


def _make_payload(
    health: int,
    max_health: int,
    items: list | None = None,
    nested_format: bool = False,
) -> dict:
    if items is None:
        items = [{"item_name": "item_armlet", "cooldown": 0}]

    if nested_format:
        slot_items = {}
        for i, item in enumerate(items):
            slot_items[f"slot{i}"] = {
                "name": item["item_name"],
                "cooldown": item["cooldown"],
            }
        return {
            "hero": {
                "team2": {
                    "player0": {
                        "health": health,
                        "max_health": max_health,
                    }
                }
            },
            "items": {
                "team2": {
                    "player0": slot_items,
                }
            },
        }

    return {
        "hero": {
            "health": health,
            "max_health": max_health,
            "items": items,
        },
    }


def _make_settings(threshold: float = 0.25, toggle_min_interval: float = 0.0) -> Settings:
    s = Settings()
    object.__setattr__(s, "threshold", threshold)
    object.__setattr__(s, "toggle_min_interval", toggle_min_interval)
    return s


def _seed(settings: Settings, health: int = 1000, max_hp: int = 1000, nested_format: bool = False) -> None:
    should_toggle_armlet(_make_payload(health, max_hp, nested_format=nested_format), settings)


def _tick_activate(
    settings: Settings,
    health: int = 200,
    max_hp: int = 1000,
    items: list | None = None,
) -> dict:
    """Simulate: seed → low HP → activate → confirm with armlet ON max_hp."""
    # tick 1: seed
    _seed(settings)
    # tick 2: low HP → triggers activate
    r = should_toggle_armlet(_make_payload(health, max_hp, items), settings)
    assert r["action"] == "activate"
    # tick 3+: confirm (armlet ON → +550 max_hp)
    r = should_toggle_armlet(_make_payload(health, max_hp + ARMLET_HP_BONUS, items), settings)
    assert r["action"] == "none"
    assert r["reason"] == "confirming_toggle"
    return r


ARMLET_HP_BONUS = 550


class TestShouldToggleArmlet:
    def test_no_armlet_resets_state(self):
        """When armlet disappears, state resets."""
        settings = _make_settings()
        _seed(settings)
        # first confirm we had state
        r = should_toggle_armlet(_make_payload(200, 1000, [{"item_name": "item_boots", "cooldown": 0}]), settings)
        assert r["action"] == "none"
        assert r["reason"] == "not_found"
        # re-seed on next armlet detection
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["reason"] == "seeding"

    def test_hp_above_threshold_no_action(self):
        settings = _make_settings(threshold=0.25)
        _seed(settings)
        payload = _make_payload(health=800, max_health=1000)
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "none"
        assert result["reason"] == "hp_above_threshold"

    def test_hp_below_threshold_activates_with_confirm(self):
        settings = _make_settings(threshold=0.25)
        _seed(settings)
        payload = _make_payload(health=200, max_health=1000)
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "activate"
        assert result["reason"] == "low_hp"

        # Next tick: GSI shows max_hp increased → confirm ON
        result = should_toggle_armlet(_make_payload(health=200, max_health=1550), settings)
        assert result["action"] == "none"
        assert result["reason"] == "confirming_toggle"
        assert result["armlet_status"] == "active"

    def test_no_armlet_in_inventory(self):
        settings = _make_settings(threshold=0.25)
        _seed(settings)
        payload = _make_payload(health=200, max_health=1000, items=[{"item_name": "item_boots", "cooldown": 0}])
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "none"
        assert result["reason"] == "not_found"

    def test_hero_dead_no_action(self):
        settings = _make_settings()
        _seed(settings)
        payload = _make_payload(health=0, max_health=1000)
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "none"
        assert result["reason"] == "dead"

    def test_activate_then_deactivate_when_hp_recovers(self):
        settings = _make_settings(threshold=0.25)
        _tick_activate(settings)

        # Armlet ON → max_hp=1550, deactivate threshold = 60% of 1550 = 930
        result = should_toggle_armlet(_make_payload(health=1000, max_health=1550), settings)
        assert result["action"] == "deactivate"
        assert result["reason"] == "hp_recovered"

        # Confirm deactivation: max_hp drops back to 1000
        result = should_toggle_armlet(_make_payload(health=1000, max_health=1000), settings)
        assert result["action"] == "none"
        assert result["reason"] == "confirming_toggle"

    def test_armlet_stays_active_while_hp_low(self):
        """With armlet ON and HP below threshold, script triggers panic combo (not keeping_active)."""
        settings = _make_settings(threshold=0.25)
        _tick_activate(settings)

        # HP below threshold with armlet ON → panic combo starts
        result = should_toggle_armlet(_make_payload(health=200, max_health=1550), settings)
        assert result["action"] == "deactivate"
        assert result["reason"] == "panic_combo_off"

    def test_debounce_blocks_rapid_toggle(self):
        """After an action, can't activate again until toggle_min_interval elapses."""
        armlet_logic.CONFIRM_TIMEOUT_SECONDS = 0.0
        settings = _make_settings(threshold=0.25, toggle_min_interval=99.0)
        _seed(settings)

        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

        # Confirm times out instantly
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["reason"] == "confirming_toggle"

        # Now debounced (armlet OFF, can_act=False)
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["reason"] == "debounced"

    def test_confirm_timeout_press_failed(self):
        """If no max_hp change after CONFIRM_TIMEOUT_SECONDS, cancel confirm."""
        armlet_logic.CONFIRM_TIMEOUT_SECONDS = 0.0
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

        # Instant timeout
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["reason"] == "confirming_toggle"

        # Confirm cancelled, armlet OFF, retries activate immediately
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

    def test_external_toggle_passive_detection(self):
        """If armlet gets toggled manually (no pending confirm), detect via passive delta."""
        armlet_logic.EXTERNAL_GRACE_SECONDS = 0.0
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # max_hp goes up by 550 externally → detect as external activation
        r = should_toggle_armlet(_make_payload(800, 1550), settings)
        assert r["reason"] == "keeping_active"
        assert r["armlet_status"] == "active"

        # max_hp drops back externally → detect as external deactivation
        r = should_toggle_armlet(_make_payload(800, 1000), settings)
        assert r["reason"] == "hp_above_threshold"
        assert r["armlet_status"] == "inactive"

    def test_nested_gsi_format(self):
        settings = _make_settings(threshold=0.25)
        _seed(settings, nested_format=True)
        payload = _make_payload(health=200, max_health=1000, nested_format=True)
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "activate"

    def test_custom_threshold(self):
        settings = _make_settings(threshold=0.50)
        _seed(settings, health=400, max_hp=1000)
        payload = _make_payload(health=400, max_health=1000)
        result = should_toggle_armlet(payload, settings)
        assert result["action"] == "activate"

    def test_passive_detection_staggered_armlet_bonus(self):
        """Reproduce real log: armlet bonus arrives spread across 3 GSI ticks."""
        settings = _make_settings(threshold=0.25)
        _seed(settings, health=307, max_hp=758)
        ticks = [
            (307, 758),
            (450, 1044),
            (600, 1220),
            (700, 1308),
        ]
        for health, max_hp in ticks:
            should_toggle_armlet(_make_payload(health, max_hp), settings)
        assert armlet_logic._armlet_active is True

    def test_passive_no_false_positive_on_pure_level(self):
        """Gradual level-up without armlet bonus should not trigger activation."""
        settings = _make_settings(threshold=0.25)
        _seed(settings)
        ticks = [
            (800, 758),
            (900, 900),
            (950, 950),
            (950, 950),
        ]
        for health, max_hp in ticks:
            r = should_toggle_armlet(_make_payload(health, max_hp), settings)
            assert r["armlet_status"] == "inactive"

    def test_external_grace_blocks_immediate_action(self):
        """After an external toggle, script does not initiate new actions during grace."""
        settings = _make_settings(threshold=0.25)
        _seed(settings, health=800, max_hp=1000)

        # External toggle ON: grace starts immediately on same tick
        r = should_toggle_armlet(_make_payload(800, 1550), settings)
        assert r["reason"] == "external_grace"
        assert r["armlet_status"] == "active"

        # Next tick: HP above threshold → grace still blocks (HP not below threshold)
        r = should_toggle_armlet(_make_payload(500, 1550), settings)
        assert r["reason"] == "external_grace"

    def test_external_grace_expires_and_retakes_control(self):
        """After grace expires, script resumes normal decisions."""
        armlet_logic.EXTERNAL_GRACE_SECONDS = 0.0
        armlet_logic.EXTERNAL_GRACE_SECONDS_CRITICAL = 0.0
        settings = _make_settings(threshold=0.25)
        _seed(settings, health=800, max_hp=1000)

        # External toggle ON: grace=0 → expires same tick, falls through to decision
        r = should_toggle_armlet(_make_payload(800, 1550), settings)
        assert r["reason"] == "keeping_active"
        assert r["armlet_status"] == "active"

        # External toggle OFF with HP low → grace expired, script activates
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

    def test_confirm_retry_on_zero_delta(self):
        """If delta stays zero after CONFIRM_RETRY_SECONDS, re-send the press immediately."""
        armlet_logic.CONFIRM_RETRY_SECONDS = 0.0  # expire instantly for test
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # tick: activate
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

        # tick: delta still zero → retry
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"
        assert r["reason"] == "confirm_retry"

    def test_confirm_retry_not_triggered_when_delta_growing(self):
        """If delta is growing (partial bonus arriving), do NOT retry — just wait."""
        armlet_logic.CONFIRM_RETRY_SECONDS = 0.0
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # tick: activate
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        assert r["action"] == "activate"

        # tick: partial bonus arrived (delta=176, not zero) → keep waiting
        r = should_toggle_armlet(_make_payload(200, 1176), settings)
        assert r["action"] == "none"
        assert r["reason"] == "confirming_toggle"

    def test_external_grace_critical_hp_uses_short_grace(self):
        """When external deactivation happens at critical HP, grace is short so script acts fast."""
        armlet_logic.EXTERNAL_GRACE_SECONDS_CRITICAL = 0.0  # expire instantly for test
        armlet_logic.EXTERNAL_GRACE_SECONDS = 99.0  # make sure normal grace would block
        settings = _make_settings(threshold=0.25)
        _seed(settings, health=800, max_hp=1000)

        # Seed armlet as active via external toggle (grace=99s but HP is high, won't matter)
        armlet_logic.EXTERNAL_GRACE_SECONDS = 0.0
        r = should_toggle_armlet(_make_payload(800, 1550), settings)
        assert r["armlet_status"] == "active"

        # External deactivation with HP already critical → critical grace (0.0 in test)
        armlet_logic.EXTERNAL_GRACE_SECONDS = 99.0
        r = should_toggle_armlet(_make_payload(200, 1000), settings)
        # grace expired instantly → script should activate immediately
        assert r["action"] == "activate"
        assert r["reason"] == "low_hp"

    def test_panic_combo_triggers_on_critical_hp(self):
        """When HP drops below threshold with armlet ON, trigger panic combo."""
        settings = _make_settings(threshold=0.25)
        # Seed con HP ya cerca del threshold para que delta no sea masivo
        should_toggle_armlet(_make_payload(270, 1550), settings)

        # Set state: armlet ON
        armlet_logic._armlet_active = True
        armlet_logic._passive_anchor = 1550
        armlet_logic._last_action_time = None
        armlet_logic._external_grace_until = 0.0

        # HP below threshold (200/1550 = 12.9% < 25%) → panic combo starts (deactivate)
        r = should_toggle_armlet(_make_payload(200, 1550), settings)
        assert r["action"] == "deactivate"
        assert r["reason"] == "panic_combo_off"
        assert armlet_logic._combo_mode is True

        # Next tick: armlet OFF confirmed (max_hp drops)
        r = should_toggle_armlet(_make_payload(150, 1000), settings)
        assert r["reason"] == "confirming_toggle"

        # Combo continues: HP still below threshold → activate
        r = should_toggle_armlet(_make_payload(150, 1000), settings)
        assert r["action"] == "activate"
        assert r["reason"] == "panic_combo_on"
        assert armlet_logic._combo_mode is False

    def test_panic_combo_cancelled_if_hp_recovers(self):
        """If HP recovers above threshold during combo, cancel it."""
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # Start combo mid-state
        armlet_logic._armlet_active = True
        armlet_logic._combo_mode = True
        armlet_logic._passive_anchor = 1550
        armlet_logic._last_action_time = None

        # HP recovered above threshold → combo cancelled
        r = should_toggle_armlet(_make_payload(500, 1000), settings)
        assert armlet_logic._combo_mode is False

    def test_panic_combo_not_triggered_during_massive_damage(self):
        """Don't trigger panic combo if taking massive damage burst."""
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # Simulate massive damage: lost 300 HP in one tick (> 5% of 1550)
        armlet_logic._armlet_active = True
        armlet_logic._passive_anchor = 1550
        armlet_logic._last_health = 500
        armlet_logic._last_action_time = None

        # HP below threshold but taking massive damage → don't combo
        r = should_toggle_armlet(_make_payload(200, 1550), settings)
        assert r["action"] == "none"
        assert r["reason"] == "keeping_active"
        assert armlet_logic._combo_mode is False

    def test_panic_combo_interrupted_by_external_toggle(self):
        """If player manually toggles during combo, combo is cancelled."""
        armlet_logic.EXTERNAL_GRACE_SECONDS = 0.0
        armlet_logic.EXTERNAL_GRACE_SECONDS_CRITICAL = 0.0
        settings = _make_settings(threshold=0.25)
        _seed(settings)

        # Start combo mid-state
        armlet_logic._armlet_active = False
        armlet_logic._combo_mode = True
        armlet_logic._passive_anchor = 1000

        # External toggle (player activates manually)
        r = should_toggle_armlet(_make_payload(200, 1550), settings)
        assert armlet_logic._combo_mode is False
        assert armlet_logic._armlet_active is True
