import os
import logging

logger = logging.getLogger(__name__)


class Settings:
    ARMLET_DEACTIVATE_THRESHOLD: float = float(os.getenv("ARMLET_DEACTIVATE_THRESHOLD", "0.60"))

    def __init__(self) -> None:
        raw_threshold = os.environ.get("ARMLET_THRESHOLD", "0.25")
        raw_key = os.environ.get("ARMLET_KEY", "1")
        raw_dry_run = os.environ.get("DRY_RUN", "false")
        raw_port = os.environ.get("GSI_PORT", "3000")
        raw_log_file = os.environ.get("LOG_FILE", "armlet.log")
        raw_combat_delta_pct = os.environ.get("ARMLET_COMBAT_DELTA_PCT", "0.05")
        raw_toggle_min_interval = os.environ.get("ARMLET_TOGGLE_MIN_INTERVAL", "1.0")

        self.threshold: float = self._parse_float(raw_threshold, 0.25)
        if not (0.0 <= self.threshold <= 1.0):
            logger.warning("ARMLET_THRESHOLD out of range [0.0, 1.0], using default 0.25")
            self.threshold = 0.25

        self.key: str = raw_key.strip() or "x"

        self.dry_run: bool = raw_dry_run.strip().lower() in ("true", "1", "yes")

        self.port: int = self._parse_int(raw_port, 3000)
        if not (1 <= self.port <= 65535):
            logger.warning("GSI_PORT out of range, using default 3000")
            self.port = 3000

        self.log_file: str = raw_log_file.strip() or "armlet.log"

        self.combat_delta_pct: float = self._parse_float(raw_combat_delta_pct, 0.05)
        if not (0.0 <= self.combat_delta_pct <= 1.0):
            logger.warning("ARMLET_COMBAT_DELTA_PCT out of range [0.0, 1.0], using default 0.05")
            self.combat_delta_pct = 0.05

        self.toggle_min_interval: float = self._parse_float(raw_toggle_min_interval, 1.0)
        if self.toggle_min_interval < 0.5:
            logger.warning("ARMLET_TOGGLE_MIN_INTERVAL muy bajo (min 0.5s), usando default 1.0")
            self.toggle_min_interval = 1.0

        # clase Settings.ARMLET_DEACTIVATE_THRESHOLD se lee del env en la línea de clase

    def threshold_hp(self, max_health: int) -> int:
        return int(max_health * self.threshold)

    @property
    def armlet_key(self) -> str:
        return self.key

    @staticmethod
    def _parse_float(value: str, default: float) -> float:
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning("Failed to parse float from '%s', using default %s", value, default)
            return default

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning("Failed to parse int from '%s', using default %s", value, default)
            return default
