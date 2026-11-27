#!/usr/bin/env python3
"""Build the executable of Sanguosha for this platform."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parent


def build(
    *,
    onedir: bool = False,
    debug: bool = False,
    name: str = "sanguosha",
    output_dir: Path = PROJECT_ROOT / "dist",
) -> int:
    """Build in a temporary directory and publish a new artifact."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("产物名称必须是单个文件名")
    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    artifact_name = name if onedir else executable_name
    output_dir = output_dir.resolve()
    destination = output_dir / artifact_name
    if destination.exists() or destination.is_symlink():
        print(f"产物已存在，请指定新的 --name 或 --output-dir：{destination}", file=sys.stderr)
        return 1

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(PROJECT_ROOT / "main.py"),
        f"--name={name}",
        *[
            f"--add-data={PROJECT_ROOT / 'data' / filename}:data"
            for filename in (
                "cards.json",
                "heroes.json",
                "heroes_new.json",
                "card_effects.json",
                "skill_config.json",
                "skill_dsl.json",
            )
        ],
        f"--add-data={PROJECT_ROOT / 'i18n' / '*.json'}:i18n",
        f"--add-data={PROJECT_ROOT / 'ui' / 'textual_ui' / 'styles'}:ui/textual_ui/styles",
        "--collect-submodules=game",
        "--collect-submodules=ai",
        "--collect-submodules=ui",
        "--collect-submodules=net",
        "--collect-submodules=i18n",
        "--collect-submodules=tools",
        "--collect-submodules=rich",
        "--collect-submodules=textual",
        "--hidden-import=logging_config",
        "--copy-metadata=sanguosha",
        f"--paths={PROJECT_ROOT}",
        "--exclude-module=pytest",
        "--exclude-module=_pytest",
        "--exclude-module=hypothesis",
        "--exclude-module=mypy",
        "--exclude-module=ruff",
        "--console",
        "--python-option=X utf8",
        "--noconfirm",
        "--noupx",
        "--onedir" if onedir else "--onefile",
    ]
    if debug:
        args.append("--debug=all")
    if sys.platform == "darwin":
        args.append(f"--target-arch={platform.machine()}")

    print(f"Python {platform.python_version()} ({platform.machine()})", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".build-", dir=output_dir) as staging_path:
        staging = Path(staging_path)
        result = subprocess.run(
            [
                *args,
                f"--distpath={staging / 'dist'}",
                f"--workpath={staging / 'work'}",
                f"--specpath={staging}",
            ],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode:
            return result.returncode

        artifact = staging / "dist" / artifact_name
        executable = artifact / executable_name if onedir else artifact
        if not executable.is_file() or not executable.stat().st_size:
            print(f"构建完成但未找到可执行文件：{executable}", file=sys.stderr)
            return 1

        # 目录模式用原子重命名。单文件模式用硬链接避免并发构建覆盖已发布文件。
        try:
            if onedir:
                artifact.rename(destination)
            if not onedir:
                destination.hardlink_to(artifact)
        except FileExistsError:
            print(f"产物已存在，请指定新的 --name 或 --output-dir：{destination}", file=sys.stderr)
            return 1

    print(f"Output: {destination}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onedir", action="store_true", help="构建目录模式")
    parser.add_argument("--debug", action="store_true", help="保留调试输出")
    parser.add_argument("--name", default="sanguosha", help="产物名称")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist", help="产物目录")
    args = parser.parse_args()
    sys.exit(
        build(onedir=args.onedir, debug=args.debug, name=args.name, output_dir=args.output_dir)
    )
