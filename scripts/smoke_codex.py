#!/usr/bin/env python3
"""通过 Codex 本地目录 RPC 验证临时插件副本，不安装插件或启动模型会话。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


async def smoke(root: Path, timeout: float) -> None:
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("SKIP: 未找到 Codex CLI")
    with tempfile.TemporaryDirectory(prefix="cc-dual-codex-") as temporary:
        base = Path(temporary)
        package = base / "plugin cache with spaces"
        package.mkdir()
        for name in ("plugins", ".agents"):
            shutil.copytree(root / name, package / name, ignore=shutil.ignore_patterns("__pycache__"))
        elsewhere = base / "unrelated cwd"
        elsewhere.mkdir()
        before = snapshot(package)
        marketplace = package / ".agents" / "plugins" / "marketplace.json"
        entries = json.loads(marketplace.read_text(encoding="utf-8"))["plugins"]
        process = await asyncio.create_subprocess_exec(
            executable, "app-server", "--stdio", cwd=elsewhere,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def call(identifier: int, method: str, params: dict) -> dict:
            request = {"id": identifier, "method": method, "params": params}
            process.stdin.write((json.dumps(request) + "\n").encode())
            await process.stdin.drain()

            async def response():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        raise RuntimeError("Codex app-server 在返回结果前退出")
                    message = json.loads(line)
                    if message.get("id") == identifier:
                        if "error" in message:
                            raise RuntimeError(f"{method}: {message['error']}")
                        return message["result"]
            return await asyncio.wait_for(response(), timeout)

        try:
            await call(1, "initialize", {"clientInfo": {"name": "cc-marketplace-compat", "version": "1.0.0"},
                                         "capabilities": {"experimentalApi": True}})
            process.stdin.write(b'{"method":"initialized"}\n')
            for identifier, entry in enumerate(entries, 2):
                name = entry["name"]
                result = await call(identifier, "plugin/read", {"marketplacePath": str(marketplace), "pluginName": name})
                plugin = result["plugin"]
                plugin_root = (package / entry["source"]["path"]).resolve()
                expected = {f"{name}:{p.parent.name}": p.resolve() for p in (plugin_root / "skills").glob("*/SKILL.md")}
                actual = {s["name"]: Path(s["path"]).resolve() for s in plugin["skills"]}
                if actual != expected or not all(s["enabled"] for s in plugin["skills"]):
                    raise RuntimeError(f"{name}: 实际加载的技能名称、启用状态或路径与包不一致")
                if plugin["marketplacePath"] != str(marketplace):
                    raise RuntimeError(f"{name}: 未从指定临时 marketplace 加载")
                if not all(s.get("interface", {}).get("displayName") for s in plugin["skills"]):
                    raise RuntimeError(f"{name}: 未加载 agents/openai.yaml 的界面元数据")
                print(f"PASS {name}: {', '.join(sorted(actual))}", flush=True)
        finally:
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        if before != snapshot(package):
            raise RuntimeError("Codex 目录读取修改了插件副本")
        print("PASS 临时缓存路径含空格、独立 CWD、插件内容保持只读。")
        print("范围：目录发现与技能元数据加载；不代表模型行为、安装流程或公共目录上架验证。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Marketplace 仓库根目录")
    parser.add_argument("--timeout", type=float, default=20, help="每个 RPC 的超时秒数（1–60）")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout 必须在 1–60 秒之间")
    try:
        asyncio.run(smoke(args.root.resolve(), args.timeout))
    except (RuntimeError, OSError, ValueError, KeyError, asyncio.TimeoutError) as error:
        print(f"Codex 加载验证未通过：{error or 'RPC 超时'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
