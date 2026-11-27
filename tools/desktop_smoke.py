"""Complete one packaged desktop practice using its process channel."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


def main(binary: Path) -> None:
    with TemporaryDirectory() as directory:
        workdir = Path(directory)
        env = os.environ.copy()
        env["SANGUOSHA_DATA_HOME"] = directory
        env.pop("SANGUOSHA_LOG_FILE", None)
        child = subprocess.Popen(
            [binary, "--desktop-practice"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            encoding="utf-8", cwd=binary.anchor, env=env,
        )
        try:
            stdin, stdout = child.stdin, child.stdout
            assert stdin is not None and stdout is not None
            state = json.loads(stdout.readline())
            assert state["screen"] == "MainMenuScreen"

            def send(kind: str, value: str = "") -> None:
                nonlocal state
                command = {"revision": state["revision"], "kind": kind, "value": value}
                stdin.write(json.dumps(command) + "\n")
                stdin.flush()
                if kind != "quit":
                    state = json.loads(stdout.readline())

            send("button", "btn-practice")
            assert state["screen"] == "HeroSelectScreen"
            send("key", "enter")
            assert state["canPlay"]
            send("key", "1")
            assert state["screen"] == "TargetSelectModal"
            send("key", "enter")
            send("key", "e")
            assert state["screen"] == "DiscardModal"
            for key in ("enter", "tab", "enter", "tab", "enter",
                        "shift+tab", "shift+tab", "shift+tab", "enter"):
                send("key", key)
            assert state["screen"] == "ShanResponseModal"
            send("key", "enter")

            deadline = time.monotonic() + 10
            while not state["canPlay"] and time.monotonic() < deadline:
                time.sleep(0.1)
                send("refresh")
            assert state["canPlay"]
            send("key", "2")
            send("key", "enter")
            assert state["screen"] == "GameOverScreen"
            send("button", "btn-report")
            assert state["screen"] == "MatchReportScreen"
            assert any(event["kind"] == "game_over" for event in state["events"])
            send("quit")
            assert child.wait(timeout=15) == 0
            assert (workdir / "match_history.json").is_file()
            assert (workdir / "desktop-practice.log").is_file()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            if child.stdin is not None:
                child.stdin.close()
            if child.stdout is not None:
                child.stdout.close()
    print("Desktop sidecar finished the practice, saved the report and exited.")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
