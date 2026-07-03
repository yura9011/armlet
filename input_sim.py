import json
import logging
import os
import socket
import subprocess
import shutil
import time

logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/auto-armlet-uinput.sock"


class InputSimulator:
    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._method = None
        self._dota_window = None
        self._uinput_dev = None
        self._pynput_ctrl = None
        if not dry_run:
            self._method = self._pick_method()

    def _find_dota_window(self) -> str | None:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", "Dota 2"],
                capture_output=True, text=True, timeout=2,
            )
            if result.stdout.strip():
                return result.stdout.strip().split()[0]
        except Exception:
            pass
        return None

    def _pick_method(self) -> str | None:
        # 1) uinput daemon socket (preferred – persists across server restarts)
        if os.path.exists(SOCKET_PATH):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(SOCKET_PATH)
                s.close()
                logger.info("InputSimulator using uinput daemon (%s)", SOCKET_PATH)
                return "daemon"
            except Exception as exc:
                logger.warning("uinput daemon socket found but connect failed: %s", exc)

        # 2) xdotool with Dota 2 window
        if shutil.which("xdotool"):
            win = self._find_dota_window()
            if win:
                self._dota_window = win
                try:
                    subprocess.run(
                        ["xdotool", "key", "--window", win, "x"],
                        capture_output=True, timeout=2,
                    )
                    logger.info("InputSimulator using xdotool (window=%s)", win)
                    return "xdotool_window"
                except Exception as exc:
                    logger.warning("xdotool window failed: %s", exc)

        # 3) uinput via evdev (direct)
        try:
            from evdev import UInput, ecodes as e
            ui = UInput({e.EV_KEY: [e.KEY_1, e.KEY_2, e.KEY_3, e.KEY_4, e.KEY_5,
                                     e.KEY_6, e.KEY_7, e.KEY_8, e.KEY_9, e.KEY_0,
                                     e.KEY_Q, e.KEY_W, e.KEY_E, e.KEY_R, e.KEY_T,
                                     e.KEY_Y, e.KEY_U, e.KEY_I, e.KEY_O, e.KEY_P,
                                     e.KEY_A, e.KEY_S, e.KEY_D, e.KEY_F, e.KEY_G,
                                     e.KEY_H, e.KEY_J, e.KEY_K, e.KEY_L, e.KEY_Z,
                                     e.KEY_X, e.KEY_C, e.KEY_V, e.KEY_B, e.KEY_N,
                                     e.KEY_M, e.KEY_SPACE]},
                         name="auto-armlet-uinput")
            self._uinput_dev = ui
            logger.info("InputSimulator using evdev uinput")
            return "evdev"
        except Exception as exc:
            logger.warning("evdev uinput failed: %s", exc)

        # 4) ydotool
        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "key", "x"], capture_output=True, timeout=2)
                logger.info("InputSimulator using ydotool")
                return "ydotool"
            except Exception as exc:
                logger.warning("ydotool failed: %s", exc)

        # 5) pynput as last resort
        try:
            from pynput.keyboard import Controller
            self._pynput_ctrl = Controller()
            logger.info("InputSimulator using pynput")
            return "pynput"
        except Exception as exc:
            logger.warning("pynput failed: %s", exc)

        logger.warning("No input method available, falling back to dry-run")
        self._dry_run = True
        return None

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def press_key(self, key: str) -> None:
        if self._dry_run:
            logger.info("[DRY-RUN] Would press key '%s'", key)
            return

        if self._method == "daemon":
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect(SOCKET_PATH)
                s.sendall(json.dumps({"key": key}).encode())
                s.close()
                logger.info("Pressed key '%s' via uinput daemon", key)
            except Exception as exc:
                logger.error("uinput daemon failed for key '%s': %s", key, exc)

        elif self._method == "xdotool_window":
            try:
                subprocess.run(
                    ["xdotool", "key", "--window", self._dota_window, key],
                    check=True, timeout=2,
                )
                logger.info("Pressed key '%s' via xdotool (window=%s)", key, self._dota_window)
            except Exception as exc:
                logger.error("xdotool window failed for key '%s': %s", key, exc)

        elif self._method == "evdev":
            try:
                from evdev import ecodes as e
                k = self._key_to_ecode(key)
                self._uinput_dev.write(e.EV_KEY, k, 1)
                self._uinput_dev.write(e.EV_SYN, e.SYN_REPORT, 0)
                time.sleep(0.05)
                self._uinput_dev.write(e.EV_KEY, k, 0)
                self._uinput_dev.write(e.EV_SYN, e.SYN_REPORT, 0)
                logger.info("Pressed key '%s' via evdev uinput", key)
            except Exception as exc:
                logger.error("evdev uinput failed for key '%s': %s", key, exc)

        elif self._method == "ydotool":
            try:
                subprocess.run(["ydotool", "key", key], check=True, timeout=2)
                logger.info("Pressed key '%s' via ydotool", key)
            except Exception as exc:
                logger.error("ydotool failed for key '%s': %s", key, exc)

        elif self._method == "pynput":
            try:
                self._pynput_ctrl.press(key)
                time.sleep(0.05)
                self._pynput_ctrl.release(key)
                logger.info("Pressed key '%s' via pynput", key)
            except Exception as exc:
                logger.error("pynput failed for key '%s': %s", key, exc)

    def _key_to_ecode(self, key: str) -> int:
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
        return mapping.get(key, e.KEY_1)
