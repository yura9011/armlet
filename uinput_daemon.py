#!/usr/bin/env python3
"""Persistent uinput daemon for Auto-Armlet GSI.

Creates a uinput device once and keeps it alive. Listens on a Unix socket
for key press commands. Run this BEFORE starting Dota 2, or restart Dota
after starting this daemon.
"""

import json
import logging
import os
import socket
import sys
import time
from pathlib import Path

SOCKET_PATH = "/tmp/auto-armlet-uinput.sock"
DEVICE_NAME = "auto-armlet-uinput"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("uinput_daemon")


def _key_to_ecode(key: str) -> int | None:
    from evdev import ecodes as e
    mapping = {
        "1": e.KEY_1, "2": e.KEY_2, "3": e.KEY_3, "4": e.KEY_4, "5": e.KEY_5,
        "6": e.KEY_6, "7": e.KEY_7, "8": e.KEY_8, "9": e.KEY_9, "0": e.KEY_0,
        "q": e.KEY_Q, "w": e.KEY_W, "e": e.KEY_E, "r": e.KEY_R, "t": e.KEY_T,
        "y": e.KEY_Y, "u": e.KEY_U, "i": e.KEY_I, "o": e.KEY_O, "p": e.KEY_P,
        "a": e.KEY_A, "s": e.KEY_S, "d": e.KEY_D, "f": e.KEY_F, "g": e.KEY_G,
        "h": e.KEY_H, "j": e.KEY_J, "k": e.KEY_K, "l": e.KEY_L, "z": e.KEY_Z,
        "x": e.KEY_X, "c": e.KEY_C, "v": e.KEY_V, "b": e.KEY_B, "n": e.KEY_N,
        "m": e.KEY_M, "space": e.KEY_SPACE,
    }
    return mapping.get(key)


def _create_uinput():
    from evdev import UInput, ecodes as e
    keys = [
        e.KEY_1, e.KEY_2, e.KEY_3, e.KEY_4, e.KEY_5,
        e.KEY_6, e.KEY_7, e.KEY_8, e.KEY_9, e.KEY_0,
        e.KEY_Q, e.KEY_W, e.KEY_E, e.KEY_R, e.KEY_T,
        e.KEY_Y, e.KEY_U, e.KEY_I, e.KEY_O, e.KEY_P,
        e.KEY_A, e.KEY_S, e.KEY_D, e.KEY_F, e.KEY_G,
        e.KEY_H, e.KEY_J, e.KEY_K, e.KEY_L, e.KEY_Z,
        e.KEY_X, e.KEY_C, e.KEY_V, e.KEY_B, e.KEY_N,
        e.KEY_M, e.KEY_SPACE,
    ]
    dev = UInput({e.EV_KEY: keys}, name=DEVICE_NAME)
    logger.info("Created uinput device: %s", DEVICE_NAME)
    return dev


def _handle_client(conn, uinput_dev):
    try:
        data = conn.recv(1024)
        if not data:
            return
        msg = json.loads(data.decode())
        key = msg.get("key", "")
        from evdev import ecodes as e
        code = _key_to_ecode(key)
        if code is None:
            logger.warning("Unknown key: %s", key)
            return
        uinput_dev.write(e.EV_KEY, code, 1)
        uinput_dev.write(e.EV_SYN, e.SYN_REPORT, 0)
        time.sleep(0.05)
        uinput_dev.write(e.EV_KEY, code, 0)
        uinput_dev.write(e.EV_SYN, e.SYN_REPORT, 0)
        logger.info("Pressed key '%s' (ecode=%d)", key, code)
    except Exception as exc:
        logger.error("Client error: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
        logger.info("Removed stale socket: %s", SOCKET_PATH)

    uinput_dev = _create_uinput()
    logger.info("PID: %d", os.getpid())

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    os.chmod(SOCKET_PATH, 0o666)
    logger.info("Listening on %s", SOCKET_PATH)

    try:
        while True:
            conn, _ = server.accept()
            _handle_client(conn, uinput_dev)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.close()
        try:
            uinput_dev.close()
        except Exception:
            pass
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    main()
