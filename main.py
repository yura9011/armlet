import logging
import logging.handlers
import os
import signal
import sys

import uvicorn

from config import Settings
from input_sim import InputSimulator
from server import create_app


def setup_logging(settings: Settings) -> None:
    log_format = (
        "%(asctime)s.%(msecs)03dZ %(levelname)-8s %(name)s %(message)s"
    )
    date_format = "%Y-%m-%dT%H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(stream_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=2,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)


def main() -> None:
    settings = Settings()
    setup_logging(settings)

    logger = logging.getLogger(__name__)
    logger.info("Starting Auto-Armlet GSI server")
    logger.info("Config: threshold=%.0f%% key=%s dry_run=%s port=%d",
        settings.threshold * 100,
        settings.key,
        settings.dry_run,
        settings.port,
    )

    simulator = InputSimulator(dry_run=settings.dry_run)
    app = create_app(settings, simulator)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=settings.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Received signal %s, shutting down gracefully", signum)
        server.should_exit = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.run()


if __name__ == "__main__":
    main()
