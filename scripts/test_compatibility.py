"""覆盖跨平台配置漂移、资源打包和与 CWD 无关的实际脚本执行。"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from validate_marketplace import Invalid, ROOT, frontmatter, read_object, validate


class MarketplaceContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cc-dual-validation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "marketplace"
        self.root.mkdir()
        for name in ("plugins", ".agents", ".claude-plugin", "docs"):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("README.md", "AGENTS.md", "CLAUDE.md"):
            shutil.copy2(ROOT / name, self.root / name)
        # README 的验证说明链接到仓库脚本。
        shutil.copytree(ROOT / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))

    def update_json(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False))

    def test_current_package_and_existing_invocation_policies(self):
        self.assertEqual(validate(self.root), {"plugins": 2, "skills": 5})
        explicit = {"skill-forge", "init", "work"}
        for path in self.root.glob("plugins/*/skills/*/SKILL.md"):
            metadata = frontmatter(path)
            policy = read_object(path.parent / "agents/openai.yaml")["policy"]
            self.assertEqual(metadata.get("disable-model-invocation", False), path.parent.name in explicit)
            self.assertEqual(policy["allow_implicit_invocation"], path.parent.name not in explicit)

    def test_missing_codex_manifest_fails(self):
        (self.root / "plugins/nuclio-plugin/.codex-plugin/plugin.json").unlink()
        with self.assertRaisesRegex(Invalid, "plugin.json"):
            validate(self.root)

    def test_version_drift_fails(self):
        self.update_json("plugins/dev-stack/.codex-plugin/plugin.json", lambda d: d.update(version="9.0.0"))
        with self.assertRaisesRegex(Invalid, "version"):
            validate(self.root)

    def test_source_cannot_escape_marketplace(self):
        self.update_json(".agents/plugins/marketplace.json", lambda d: d["plugins"][0]["source"].update(path="./../outside"))
        with self.assertRaisesRegex(Invalid, "source 路径越界"):
            validate(self.root)

    def test_source_cannot_escape_through_symlink(self):
        outside = self.root.parent / "external-plugin"
        outside.mkdir()
        (self.root / "plugins/escape").symlink_to(outside, target_is_directory=True)
        self.update_json(".agents/plugins/marketplace.json", lambda d: d["plugins"][0]["source"].update(path="./plugins/escape"))
        with self.assertRaisesRegex(Invalid, "source 路径越界"):
            validate(self.root)

    def test_unregistered_plugin_fails(self):
        shutil.copytree(self.root / "plugins/dev-stack", self.root / "plugins/unregistered")
        with self.assertRaisesRegex(Invalid, "未注册"):
            validate(self.root)

    def test_implicit_invocation_drift_fails(self):
        path = self.root / "plugins/nuclio-plugin/skills/work/agents/openai.yaml"
        path.write_text(path.read_text().replace("allow_implicit_invocation: false", "allow_implicit_invocation: true"))
        with self.assertRaisesRegex(Invalid, "调用策略"):
            validate(self.root)

    def test_duplicate_yaml_policy_fails(self):
        path = self.root / "plugins/nuclio-plugin/skills/work/agents/openai.yaml"
        path.write_text(path.read_text() + "policy:\n  allow_implicit_invocation: true\n")
        with self.assertRaisesRegex(Invalid, "重复配置键"):
            validate(self.root)

    def test_non_string_yaml_key_is_a_validation_error(self):
        path = self.root / "plugins/nuclio-plugin/skills/work/agents/openai.yaml"
        path.write_text(path.read_text() + "? [unexpected, key]\n: value\n")
        with self.assertRaisesRegex(Invalid, "配置键必须为字符串"):
            validate(self.root)

    def test_missing_shared_reference_fails(self):
        (self.root / "plugins/nuclio-plugin/references/host-runtime.md").unlink()
        with self.assertRaisesRegex(Invalid, "链接资源不存在"):
            validate(self.root)


class RelocatedRuntime(unittest.TestCase):
    def test_scripts_use_explicit_project_instead_of_cwd_or_claude_environment(self):
        with tempfile.TemporaryDirectory(prefix="cc-dual-runtime-") as temporary:
            base = Path(temporary)
            cache = base / "plugin cache with spaces"
            shutil.copytree(ROOT / "plugins", cache, ignore=shutil.ignore_patterns("__pycache__"))
            project = base / "target project"
            project.mkdir()
            elsewhere = base / "unrelated cwd"
            elsewhere.mkdir()
            env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
            env["PYTHONDONTWRITEBYTECODE"] = "1"

            def run(*args):
                result = subprocess.run(args, cwd=elsewhere, env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            run("git", "-c", "init.templateDir=", "init", "-q", "-b", "main", str(project))
            run("git", "-C", str(project), "-c", "user.name=Compatibility Test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-q", "--allow-empty", "-m", "fixture")
            (project / ".dev-docs/changes/archive").mkdir(parents=True)
            before = {str(p.relative_to(cache)): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
            runtime = cache / "nuclio-plugin/scripts/change.py"
            created = json.loads(run(sys.executable, "-B", str(runtime), "--project-root", str(project), "create",
                                     "--id", "relocated", "--title", "路径验证", "--goal", "只写入显式目标项目"))
            self.assertTrue(created["ok"])
            # 从另一条宿主入口读取同一份状态，无需转换 artifact。
            status = json.loads(run(sys.executable, "-B", str(runtime), "--project-root", str(project),
                                    "status", "--id", "relocated", "--json"))
            self.assertTrue(status["ok"])
            self.assertEqual({p.name for p in (project / ".dev-docs/changes/relocated").iterdir()},
                             {"change.md", "delivery.yaml", "state.yaml"})
            run_dir = project / ".skill-forge/portable-runtime"
            run_dir.mkdir(parents=True)
            spec = run_dir / "spec.md"
            spec.write_text("# 兼容性合同\n\n保持共享脚本与显式项目目录。\n")
            validator = cache / "dev-stack/skills/skill-forge/scripts/plan_contract.py"
            digest = run(sys.executable, "-B", str(validator), "hash-spec", str(spec)).strip()
            self.assertEqual(digest, hashlib.sha256(spec.read_bytes()).hexdigest())
            plan = run_dir / "plan.yaml"
            plan.write_text(json.dumps({
                "schema_version": 1, "spec": "spec.md", "spec_sha256": digest,
                "impacts": {"trigger_or_behavior_changed": False, "script_changed": False,
                            "agent_permissions_changed": False, "external_side_effects_changed": False},
                "tasks": [{"id": 1, "name": "创建项目说明", "files": {"create": ["README.md"], "modify": [], "delete": []},
                           "steps": ["写入项目说明"], "acceptance": ["说明包含项目用途"], "checks": ["python3 --version"]}],
            }, ensure_ascii=False))
            validated = json.loads(run(sys.executable, "-B", str(validator), "validate", str(plan), "--repo-root", str(project)))
            self.assertEqual(validated["file_counts"], {"create": 1, "modify": 0, "delete": 0})
            after = {str(p.relative_to(cache)): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
