"""Complete one packaged desktop practice using its process channel."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


async def verify_lan_cli(binary: Path, workdir: Path, env: dict[str, str]) -> None:
    from net.server import GameServer

    server = GameServer(port=0, lan_preview=True)
    listening = asyncio.create_task(server.start())

    async def connect(name: str) -> asyncio.subprocess.Process:
        while not server.port:
            await asyncio.sleep(0.01)
        return await asyncio.create_subprocess_exec(
            str(binary), "--connect", f"127.0.0.1:{server.port}", "--name", name,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, cwd=workdir, env=env,
        )

    async def wait_for_line(client: asyncio.subprocess.Process, prefix: str) -> str:
        assert client.stdout is not None
        while line := await client.stdout.readline():
            message = line.decode("utf-8").strip()
            if message.startswith(prefix):
                return message.removeprefix(prefix)
        raise AssertionError(f"The LAN client exited before printing {prefix!r}")

    clients = []
    try:
        for name in ("房主", "玩家二"):
            client = await asyncio.wait_for(connect(name), timeout=10)
            clients.append(client)
            await asyncio.wait_for(wait_for_line(client, "create ["), timeout=15)
        host, guest = clients
        assert host.stdin is not None and guest.stdin is not None
        host.stdin.write(b"create 2\n")
        await host.stdin.drain()
        room_id = await asyncio.wait_for(wait_for_line(host, "房间 "), timeout=5)
        guest.stdin.write(f"join {room_id}\n".encode("utf-8"))
        await guest.stdin.drain()
        assert await asyncio.wait_for(wait_for_line(guest, "房间 "), timeout=5) == room_id
        host.stdin.write(b"quit\n")
        await host.stdin.drain()
        guest.stdin.close()
        for client in clients:
            assert await asyncio.wait_for(client.wait(), timeout=10) == 0
    finally:
        for client in clients:
            if client.returncode is None:
                client.kill()
                await client.wait()
        server.stop()
        await asyncio.wait_for(listening, timeout=10)


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
        asyncio.run(verify_lan_cli(binary, workdir, env))
    print("Desktop sidecar finished the practice, saved the report and exited.")
    print("Packaged LAN clients created and joined a loopback room, then exited on quit and EOF.")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
