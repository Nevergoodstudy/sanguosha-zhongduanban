"""Verify the arm64 release in a real terminal."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from i18n import card_name, set_locale, t


def expect(terminal: int, output: bytearray, label: str) -> None:
    """Wait for a visible Textual label or raise after the step times out."""
    wanted = label.encode()
    deadline = time.monotonic() + 15
    while wanted not in re.sub(rb"\x1b\[[0-9;]*m", b"", output):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([terminal], [], [], remaining)[0]:
            display = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", output).decode(errors="replace")
            tail = "\n".join(line.strip() for line in display.splitlines() if line.strip())
            raise RuntimeError(f"Terminal did not render {label!r}. Last output: {tail[-1800:]}")
        try:
            output.extend(os.read(terminal, 65536))
        except OSError as error:
            if error.errno == errno.EIO:
                raise RuntimeError(f"Terminal closed before rendering {label!r}") from error
            raise
    output.clear()
    print(f"Rendered {label}", flush=True)


def press(terminal: int, *keys: bytes) -> None:
    """Send keys with time for Textual to process each focus change."""
    for key in keys:
        os.write(terminal, key)
        time.sleep(0.08)


def play(terminal: int, *, practice: bool) -> None:
    """Drive a classic start or a complete practice match by keyboard."""
    output = bytearray()
    play_hint = t("ui.play.play_hint")
    target_prompt = t("ui.modal.target_for", card=card_name("sha"))
    expect(terminal, output, t("ui.menu.start").split(" ", 1)[1])
    if not practice:
        press(terminal, b"\r")
        expect(terminal, output, t("ui.setup.start").split(" ", 1)[1])
        press(terminal, b"\x1b[Z", b"\r")  # Start Game follows the last setup setting.
        expect(terminal, output, t("ui.hero.lord"))
        os.write(terminal, b"\r")
        expect(terminal, output, play_hint)
        press(terminal, b"q")
        return

    press(terminal, b"\t", b"\r")
    expect(terminal, output, t("ui.hero.practice"))
    os.write(terminal, b"\r")
    expect(terminal, output, play_hint)
    press(terminal, b"1")
    expect(terminal, output, target_prompt)
    os.write(terminal, b"\r")
    expect(terminal, output, t("combat.dodge_success", name="AI_2").strip())
    os.write(terminal, b"e")
    expect(terminal, output, t("ui.modal.discard"))
    press(
        terminal,
        b"\r",
        b"\t",
        b"\r",
        b"\t",
        b"\r",
        b"\x1b[Z",
        b"\x1b[Z",
        b"\x1b[Z",
        b"\r",
    )
    expect(terminal, output, t("ui.modal.shan"))
    os.write(terminal, b"\r")
    expect(terminal, output, play_hint)
    # The terminal may redraw the previous hint while the AI turn is winding down.
    time.sleep(0.6)
    press(terminal, b"2")
    expect(terminal, output, target_prompt)
    os.write(terminal, b"\r")
    expect(terminal, output, t("ui.result.again"))
    press(terminal, b"\t", b"\r")
    expect(terminal, output, t("ui.report.version", version="").strip())
    os.write(terminal, b"\x11")  # Ctrl+Q


def smoke(binary: Path, *, practice: bool, columns: int, rows: int, locale: str) -> None:
    """Run the executable and verify its result from a separate directory."""
    set_locale(locale)
    print(f"Running {'practice' if practice else 'classic'} at {columns}×{rows} ({locale})", flush=True)
    with TemporaryDirectory(prefix="sanguosha-smoke-") as run_dir:
        terminal, tty = pty.openpty()
        try:
            fcntl.ioctl(tty, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
            env = {
                **os.environ,
                "TERM": "xterm-256color",
                "SANGUOSHA_DATA_HOME": run_dir,
                "SANGUOSHA_LOG_FILE": str(Path(run_dir) / "game.log"),
            }
            with subprocess.Popen(
                [binary, "--lang", locale],
                cwd=run_dir,
                env=env,
                stdin=tty,
                stdout=tty,
                stderr=tty,
                start_new_session=True,
            ) as game:
                try:
                    play(terminal, practice=practice)
                    deadline = time.monotonic() + 10
                    while game.poll() is None and time.monotonic() < deadline:
                        if select.select([terminal], [], [], 0.1)[0]:
                            os.read(terminal, 65536)
                    status = game.wait(timeout=1)
                    if status:
                        raise RuntimeError(f"Game exited with status {status}")
                    print("Game exited with status 0", flush=True)
                finally:
                    if game.poll() is None:
                        os.killpg(game.pid, signal.SIGKILL)
        finally:
            os.close(tty)
            os.close(terminal)

        if practice:
            path = Path(run_dir) / "match_history.json"
            result = json.loads(path.read_text(encoding="utf-8"))["matches"][-1]
            if result["winner"] != "lord" or result["game_version"] in {"", "source"}:
                raise RuntimeError("Expected a victory and the bundled game version in the report")
            dodges = [event for event in result["events"] if event["kind"] == "dodge"]
            if len(dodges) != 2:
                raise RuntimeError("Expected both successful dodge responses in the report")
            print(f"Persisted practice victory for game version {result['game_version']}")


if __name__ == "__main__":
    binary = Path(sys.argv[1]).resolve()
    architecture = subprocess.check_output(["lipo", "-archs", binary], text=True).strip()
    if architecture != "arm64":
        sys.exit(f"Expected an arm64 executable, found {architecture}")
    subprocess.run(["codesign", "--verify", "--verbose=2", binary], check=True)
    smoke(binary, practice=False, columns=120, rows=40, locale="zh_CN")
    smoke(binary, practice=True, columns=120, rows=40, locale="en_US")
    smoke(binary, practice=True, columns=80, rows=24, locale="zh_CN")
