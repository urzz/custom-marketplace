#!/usr/bin/env python3
"""Nuclio v3 thin Runtime: contract, delivery, current checks, and archive."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

COMMANDS = ("create", "approve", "status", "record-check", "verify", "complete", "archive")
ARTIFACTS = ("change.md", "delivery.yaml", "state.yaml")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AC_RE = re.compile(r"(AC-[A-Za-z0-9-]+):\s*(.+)$")
MILESTONE_RE = re.compile(r"^M[1-9][0-9]*$")
MAX_BYTES = 1024 * 1024
KNOWLEDGE_RESULTS = {"NO_OP", "APPLIED", "PARTIAL", "REJECTED"}
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
AC_ID_RE = re.compile(r"^AC-[A-Za-z0-9-]+$")


class NuclioError(Exception):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


class UniqueKeyLoader(yaml.SafeLoader if yaml is not None else object):  # type: ignore[misc,valid-type]
    pass


def _mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise NuclioError("DUPLICATE_YAML_KEY", f"duplicate YAML mapping key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


if yaml is not None:
    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def require_yaml() -> Any:
    if yaml is None:
        raise NuclioError("DEPENDENCY_MISSING", "PyYAML is required")
    return yaml


def emit_ok(payload: dict[str, Any]) -> int:
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, separators=(",", ":")))
    return 0


def emit_error(error: NuclioError) -> int:
    payload: dict[str, Any] = {"ok": False, "code": error.code, "message": error.message}
    if error.details:
        payload["details"] = error.details
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    return 1


def root_path(value: str) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def validate_id(value: Any) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value == "archive":
        raise NuclioError("INVALID_CHANGE_ID", f"invalid change id: {value!r}")
    return value


def under(root: Path, path: Path) -> Path:
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise NuclioError("PATH_ESCAPE", f"path escapes project root: {path}") from exc
    return path


def active_dir(root: Path, change_id: str) -> Path:
    return under(root, root / ".dev-docs" / "changes" / validate_id(change_id))


def archive_dir(root: Path, change_id: str) -> Path:
    return under(root, root / ".dev-docs" / "changes" / "archive" / validate_id(change_id))


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path, label: str) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise NuclioError("MISSING_ARTIFACT", f"missing {label}: {path}") from exc
    if len(data) > MAX_BYTES:
        raise NuclioError("ARTIFACT_TOO_LARGE", f"{label} exceeds {MAX_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NuclioError("INVALID_UTF8", f"{label} must be UTF-8") from exc


def read_yaml(path: Path, label: str) -> Any:
    try:
        return require_yaml().load(read_text(path, label), Loader=UniqueKeyLoader)
    except NuclioError:
        raise
    except Exception as exc:
        raise NuclioError("INVALID_YAML", f"invalid YAML in {label}: {exc}") from exc


def dump_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            require_yaml().safe_dump(data, stream, sort_keys=False, allow_unicode=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception as exc:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass
        if isinstance(exc, NuclioError):
            raise
        raise NuclioError("STATE_WRITE_FAILED", f"failed to write {path}: {exc}") from exc


def git(root: Path, *args: str, allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if not allow_fail and result.returncode:
        raise NuclioError("GIT_ERROR", f"git {' '.join(args)} failed", stderr=result.stderr.strip())
    return result


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def require_attached_head(root: Path) -> None:
    if git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_fail=True).returncode:
        raise NuclioError("DETACHED_HEAD", "git HEAD must be attached to a branch")


def index_clean(root: Path) -> bool:
    return git(root, "diff", "--cached", "--quiet", allow_fail=True).returncode == 0


def require_clean_index(root: Path) -> None:
    if not index_clean(root):
        raise NuclioError("DIRTY_INDEX", "git index must be empty")


def porcelain(root: Path) -> list[str]:
    output = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    fields = [item for item in output.split("\0") if item]
    paths: list[str] = []
    index = 0
    while index < len(fields):
        item = fields[index]
        status, name = item[:2], item[3:]
        if status.startswith(("R", "C")) and index + 1 < len(fields):
            index += 1
            name = fields[index]
        paths.append(name)
        index += 1
    return paths


def require_product_clean(root: Path, change_id: str, allowed_dirty: set[str] | None = None) -> None:
    active_prefix = f".dev-docs/changes/{change_id}/"
    allowed = allowed_dirty or set()
    dirty = [path for path in porcelain(root) if not path.startswith(active_prefix) and path not in allowed]
    if dirty:
        raise NuclioError("DIRTY_PRODUCT_WORKTREE", "product worktree must be clean", paths=dirty)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise NuclioError("INVALID_CHANGE", "change.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise NuclioError("INVALID_CHANGE", "change.md frontmatter is not closed")
    try:
        frontmatter = require_yaml().load(text[4:end], Loader=UniqueKeyLoader)
    except NuclioError:
        raise
    except Exception as exc:
        raise NuclioError("INVALID_CHANGE", f"invalid change.md frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise NuclioError("INVALID_CHANGE", "change.md frontmatter must be a mapping")
    return frontmatter, text[end + 5:]


def sections(body: str) -> tuple[dict[str, str], list[str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, re.M))
    parsed: dict[str, str] = {}
    order: list[str] = []
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        if name in parsed:
            raise NuclioError("INVALID_CHANGE", "change.md contains duplicate section", heading=name)
        parsed[name] = body[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(body)].strip()
        order.append(name)
    return parsed, order


def parse_change(path: Path, change_id: str, *, completion: bool = False) -> dict[str, Any]:
    frontmatter, body = parse_frontmatter(read_text(path, "change.md"))
    if set(frontmatter) != {"schema_version", "change_id", "revision"}:
        raise NuclioError("INVALID_CHANGE", "change.md frontmatter keys mismatch")
    if frontmatter.get("schema_version") != 1 or frontmatter.get("change_id") != change_id:
        raise NuclioError("IDENTITY_DRIFT", "change.md identity mismatch")
    if not isinstance(frontmatter.get("revision"), int) or isinstance(frontmatter["revision"], bool) or frontmatter["revision"] < 1:
        raise NuclioError("INVALID_CHANGE", "change.md revision must be a positive integer")
    title = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ") and line[2:].strip()), None)
    if not title:
        raise NuclioError("INVALID_CHANGE", "change.md requires an H1 title")
    parsed, order = sections(body)
    required = ("Goal", "Context", "Constraints", "Non-goals", "Acceptance Criteria")
    missing = [name for name in required if not parsed.get(name)]
    if missing:
        raise NuclioError("INVALID_CHANGE", "change.md has missing or empty required sections", sections=missing)
    acceptance: dict[str, str] = {}
    for line in parsed["Acceptance Criteria"].splitlines():
        matched = re.match(r"^\s*-\s+" + AC_RE.pattern, line)
        if matched:
            ac, description = matched.group(1), matched.group(2).strip()
            if ac in acceptance:
                raise NuclioError("INVALID_CHANGE", "Acceptance IDs must be unique", acceptance=ac)
            acceptance[ac] = description
    if not acceptance:
        raise NuclioError("INVALID_CHANGE", "Acceptance Criteria must contain AC-* list items")
    if "Decisions" in parsed and not parsed["Decisions"]:
        raise NuclioError("INVALID_CHANGE", "Decisions must be non-empty when present")
    if completion:
        final = ("Outcome", "Validation", "Knowledge Updates", "Residual Risks")
        if any(not parsed.get(name) for name in final) or order[-4:] != list(final):
            raise NuclioError("INCOMPLETE_CHANGE_RECORD", "completion sections must be non-empty and appended in canonical order")
    contract = {"frontmatter": frontmatter, "title": title, "sections": {name: parsed[name] for name in required if name in parsed}}
    if "Decisions" in parsed:
        contract["sections"]["Decisions"] = parsed["Decisions"]
    return {"frontmatter": frontmatter, "title": title, "sections": parsed, "order": order, "acceptance": list(acceptance), "contract": contract}


def validate_cwd(root: Path, value: Any) -> str:
    if value is None:
        return "."
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise NuclioError("INVALID_DELIVERY", "check cwd must be a repo-relative path")
    candidate = under(root, root / value)
    if candidate.resolve(strict=False) != root and ".." in Path(value).parts:
        raise NuclioError("INVALID_DELIVERY", "check cwd cannot contain ..")
    return value


def validate_check(root: Path, raw: Any, acceptance: set[str], source: str) -> dict[str, Any]:
    allowed = {"id", "run", "cwd", "timeout_seconds"} | ({"covers"} if source == "change" else set())
    if not isinstance(raw, dict) or set(raw) - allowed or {"id", "run"} - set(raw):
        raise NuclioError("INVALID_DELIVERY", "check schema keys mismatch")
    check_id = raw["id"]
    run = raw["run"]
    if not isinstance(check_id, str) or not check_id.strip() or not isinstance(run, list) or not run or not all(isinstance(item, str) and item for item in run):
        raise NuclioError("INVALID_DELIVERY", "check id and run must be non-empty strings and argv")
    result: dict[str, Any] = {"id": check_id, "source": source, "run": list(run), "cwd": validate_cwd(root, raw.get("cwd")), "timeout_seconds": None, "covers": []}
    if "timeout_seconds" in raw:
        timeout = raw["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise NuclioError("INVALID_DELIVERY", "timeout_seconds must be a positive integer")
        result["timeout_seconds"] = timeout
    if source == "change":
        covers = raw.get("covers")
        if not isinstance(covers, list) or not covers or len(covers) != len(set(covers)) or any(item not in acceptance for item in covers):
            raise NuclioError("INVALID_DELIVERY", "change check covers must name unique Acceptance IDs")
        result["covers"] = list(covers)
    return result


def parse_delivery(root: Path, change_id: str, acceptance: list[str]) -> dict[str, Any]:
    raw = read_yaml(active_dir(root, change_id) / "delivery.yaml", "delivery.yaml")
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "change_id", "milestones", "verification"}:
        raise NuclioError("INVALID_DELIVERY", "delivery.yaml schema keys mismatch")
    if raw.get("schema_version") != 1 or raw.get("change_id") != change_id:
        raise NuclioError("IDENTITY_DRIFT", "delivery.yaml identity mismatch")
    milestones = raw.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise NuclioError("INVALID_DELIVERY", "delivery.yaml requires milestones")
    seen, covered, normalized = set(), set(), []
    for milestone in milestones:
        if not isinstance(milestone, dict) or set(milestone) != {"id", "kind", "outcome", "covers", "status", "handoff"}:
            raise NuclioError("INVALID_DELIVERY", "milestone schema keys mismatch")
        marker = milestone["id"]
        covers = milestone["covers"]
        if not isinstance(marker, str) or not MILESTONE_RE.fullmatch(marker) or marker in seen or milestone["kind"] not in {"delivery", "integration"} or not isinstance(milestone["outcome"], str) or not milestone["outcome"].strip() or milestone["status"] not in {"pending", "in_progress", "done"} or not isinstance(covers, list) or not covers or len(covers) != len(set(covers)) or any(ac not in acceptance for ac in covers):
            raise NuclioError("INVALID_DELIVERY", "invalid milestone")
        handoff = milestone["handoff"]
        if handoff is not None and (not isinstance(handoff, dict) or set(handoff) != {"summary", "remaining"} or not all(isinstance(handoff[key], str) and handoff[key].strip() for key in handoff)):
            raise NuclioError("INVALID_DELIVERY", "handoff must be null or summary and remaining")
        seen.add(marker); covered.update(covers); normalized.append(dict(milestone))
    if covered != set(acceptance):
        raise NuclioError("AC_COVERAGE_MISSING", "milestones do not cover every Acceptance", missing=sorted(set(acceptance) - covered))
    if len(normalized) > 1 and (normalized[-1]["kind"] != "integration" or set(normalized[-1]["covers"]) != set(acceptance)):
        raise NuclioError("INTEGRATION_MILESTONE_REQUIRED", "multi-milestone delivery must end with integration covering all Acceptance")
    verification = raw.get("verification")
    if not isinstance(verification, dict) or set(verification) != {"checks"} or not isinstance(verification["checks"], list):
        raise NuclioError("INVALID_DELIVERY", "verification must contain checks")
    checks = [validate_check(root, item, set(acceptance), "change") for item in verification["checks"]]
    return {"milestones": normalized, "checks": checks}


def project_checks(root: Path, acceptance: list[str]) -> list[dict[str, Any]]:
    path = root / ".dev-docs" / "nuclio.yaml"
    if not path.exists():
        return []
    raw = read_yaml(path, "nuclio.yaml")
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "checks"} or raw.get("schema_version") != 1 or not isinstance(raw["checks"], list):
        raise NuclioError("INVALID_PROJECT_CONFIG", "nuclio.yaml must contain schema_version 1 and checks")
    return [validate_check(root, item, set(acceptance), "project") for item in raw["checks"]]


def current_definition(root: Path, change_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    reject_v2_active(root, change_id)
    change = parse_change(active_dir(root, change_id) / "change.md", change_id)
    delivery = parse_delivery(root, change_id, change["acceptance"])
    checks = project_checks(root, change["acceptance"]) + delivery["checks"]
    identifiers = [check["id"] for check in checks]
    if len(identifiers) != len(set(identifiers)):
        raise NuclioError("DUPLICATE_CHECK_ID", "project and change checks must have unique IDs")
    return change, delivery, checks


def state_file(root: Path, change_id: str) -> Path:
    return active_dir(root, change_id) / "state.yaml"


def valid_sha_or_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and bool(SHA_RE.fullmatch(value)))


def validate_state(state: Any, change_id: str) -> dict[str, Any]:
    required = {"schema_version", "change_id", "revision", "phase", "base_head", "approval_head", "verified_head", "verification", "knowledge"}
    if not isinstance(state, dict) or set(state) != required or state.get("schema_version") != 1 or state.get("change_id") != change_id:
        raise NuclioError("INVALID_STATE", "state.yaml schema or identity mismatch")
    revision, phase = state["revision"], state["phase"]
    if (revision is not None and (not isinstance(revision, int) or isinstance(revision, bool) or revision < 1)) or phase not in {"shape", "build", "verified", "complete"}:
        raise NuclioError("INVALID_STATE", "state.yaml revision or phase is invalid")
    if not all(valid_sha_or_null(state[key]) for key in ("base_head", "approval_head", "verified_head")):
        raise NuclioError("INVALID_STATE", "state.yaml Git identity is invalid")
    verification = state["verification"]
    if not isinstance(verification, dict) or set(verification) != {"checks", "acceptance", "manual", "review"} or not isinstance(verification["checks"], list) or not isinstance(verification["acceptance"], dict) or not isinstance(verification["manual"], list) or verification["review"] is not None and not isinstance(verification["review"], dict):
        raise NuclioError("INVALID_STATE", "state.yaml verification is invalid")
    if any(not isinstance(ac, str) or not AC_ID_RE.fullmatch(ac) or result not in {"missing", "passed"} for ac, result in verification["acceptance"].items()):
        raise NuclioError("INVALID_STATE", "state.yaml Acceptance evidence is invalid")
    check_keys = {"id", "source", "run", "cwd", "timeout_seconds", "covers", "head", "exit_code", "summary"}
    if any(not isinstance(item, dict) or set(item) != check_keys or not isinstance(item["id"], str) or item["source"] not in {"change", "project"} or not isinstance(item["run"], list) or not item["run"] or not all(isinstance(arg, str) and arg for arg in item["run"]) or not isinstance(item["cwd"], str) or not isinstance(item["covers"], list) or not valid_sha_or_null(item["head"]) or not isinstance(item["exit_code"], int) or isinstance(item["exit_code"], bool) or not isinstance(item["summary"], str) for item in verification["checks"]):
        raise NuclioError("INVALID_STATE", "state.yaml check evidence is invalid")
    manual_keys = {"acceptance", "steps", "result", "executor", "head"}
    if any(not isinstance(item, dict) or set(item) != manual_keys or not isinstance(item["acceptance"], str) or not AC_ID_RE.fullmatch(item["acceptance"]) or not all(isinstance(item[key], str) and item[key].strip() for key in ("steps", "result", "executor")) or not valid_sha_or_null(item["head"]) for item in verification["manual"]):
        raise NuclioError("INVALID_STATE", "state.yaml manual evidence is invalid")
    review = verification["review"]
    if review is not None and (set(review) != {"status", "summary", "covers", "head"} or review["status"] not in {"PASS", "FAIL"} or not isinstance(review["summary"], str) or not review["summary"].strip() or not isinstance(review["covers"], list) or not all(isinstance(ac, str) and AC_ID_RE.fullmatch(ac) for ac in review["covers"]) or not valid_sha_or_null(review["head"])):
        raise NuclioError("INVALID_STATE", "state.yaml review evidence is invalid")
    knowledge = state["knowledge"]
    if not isinstance(knowledge, dict) or set(knowledge) != {"result", "paths"} or knowledge["result"] not in {None, *KNOWLEDGE_RESULTS} or not isinstance(knowledge["paths"], list):
        raise NuclioError("INVALID_STATE", "state.yaml knowledge is invalid")
    paths = [valid_knowledge_path(path) for path in knowledge["paths"]]
    if len(paths) != len(set(paths)) or ((knowledge["result"] in {None, "NO_OP", "REJECTED"}) and paths) or (knowledge["result"] in {"APPLIED", "PARTIAL"} and not paths):
        raise NuclioError("INVALID_STATE", "state.yaml knowledge result and paths are inconsistent")
    if revision is None and (phase != "shape" or any(state[key] is not None for key in ("base_head", "approval_head", "verified_head"))):
        raise NuclioError("INVALID_STATE", "unapproved state must be shape with null Git identities")
    if revision is not None and state["base_head"] is None:
        raise NuclioError("INVALID_STATE", "approved state requires a base identity")
    if state["approval_head"] is None and phase not in {"shape", "build"}:
        raise NuclioError("INVALID_STATE", "uncommitted approval state must be build")
    if phase == "complete" and (state["verified_head"] is None or knowledge["result"] is None):
        raise NuclioError("INVALID_STATE", "complete state requires verification and knowledge result")
    return state


def load_state(root: Path, change_id: str) -> dict[str, Any]:
    return validate_state(read_yaml(state_file(root, change_id), "state.yaml"), change_id)


def write_state(root: Path, change_id: str, state: dict[str, Any]) -> None:
    dump_atomic(state_file(root, change_id), state)


def exact_artifacts(directory: Path, *, code: str = "UNEXPECTED_ARTIFACTS") -> None:
    if not directory.is_dir():
        raise NuclioError("MISSING_CHANGE", f"change directory missing: {directory}")
    names = sorted(item.name for item in directory.iterdir())
    invalid = [name for name in ARTIFACTS if name in names and (directory / name).is_symlink()]
    if names != sorted(ARTIFACTS) or invalid:
        raise NuclioError(code, "change directory must contain exactly regular change.md, delivery.yaml, state.yaml", artifacts=names)


def reject_v2_active(root: Path, change_id: str) -> None:
    directory = active_dir(root, change_id)
    if (directory / "plan.yaml").exists():
        raise NuclioError("V2_ACTIVE_UNSUPPORTED", "v2 active changes are unsupported; archive or remove the old active change first", path=rel(root, directory / "plan.yaml"))


def contract_from_approval(root: Path, change_id: str, state: dict[str, Any]) -> dict[str, Any]:
    approval = state.get("approval_head")
    if not isinstance(approval, str) or not approval:
        raise NuclioError("NOT_APPROVED", "change has not been approved")
    pathspec = f".dev-docs/changes/{change_id}/change.md"
    result = git(root, "show", f"{approval}:{pathspec}", allow_fail=True)
    if result.returncode:
        raise NuclioError("APPROVAL_ARTIFACT_MISSING", "approval commit lacks change.md")
    # Parse committed approval data in memory.
    frontmatter, body = parse_frontmatter(result.stdout)
    parsed, _ = sections(body)
    required = ("Goal", "Context", "Constraints", "Non-goals", "Acceptance Criteria")
    title = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ") and line[2:].strip()), "")
    contract = {"frontmatter": frontmatter, "title": title, "sections": {key: parsed.get(key, "") for key in required}}
    if "Decisions" in parsed:
        contract["sections"]["Decisions"] = parsed["Decisions"]
    return contract


def require_current_contract(root: Path, change_id: str, state: dict[str, Any], change: dict[str, Any]) -> None:
    if state.get("revision") != change["frontmatter"]["revision"] or contract_from_approval(root, change_id, state) != change["contract"]:
        raise NuclioError("CONTRACT_DRIFT", "change.md differs from the approved contract; revise and approve again")


def commit_subject(root: Path) -> str:
    return git(root, "log", "-1", "--format=%s").stdout.rstrip("\n")


def commit_parent(root: Path) -> str:
    return git(root, "rev-parse", "HEAD^").stdout.strip()


def changed_paths(root: Path) -> list[str]:
    return [line for line in git(root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "HEAD").stdout.splitlines() if line]


def approval_subject(change_id: str, revision: int) -> str:
    return f"approve({change_id}): confirm revision {revision}"


def approval_paths(change_id: str) -> set[str]:
    return {f".dev-docs/changes/{change_id}/{name}" for name in ARTIFACTS}


def approval_commit_paths(root: Path, change_id: str) -> bool:
    changed, allowed = set(changed_paths(root)), approval_paths(change_id)
    required = {f".dev-docs/changes/{change_id}/change.md", f".dev-docs/changes/{change_id}/state.yaml"}
    return required <= changed <= allowed


def try_recover_approval(root: Path, change_id: str, state: dict[str, Any], revision: int) -> bool:
    if state.get("approval_head") is not None or commit_subject(root) != approval_subject(change_id, revision) or not approval_commit_paths(root, change_id):
        return False
    pathspec = f".dev-docs/changes/{change_id}/state.yaml"
    committed = git(root, "show", f"HEAD:{pathspec}", allow_fail=True)
    if committed.returncode:
        return False
    try:
        approved_state = validate_state(require_yaml().load(committed.stdout, Loader=UniqueKeyLoader), change_id)
    except (NuclioError, Exception):
        return False
    if approved_state["revision"] != revision or approved_state["base_head"] != state["base_head"] or approved_state["approval_head"] is not None or approved_state["verified_head"] is not None or approved_state["phase"] != "build":
        return False
    state["approval_head"] = head(root)
    write_state(root, change_id, state)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nuclio v3 thin Runtime")
    parser.add_argument("--project-root", default=".", help="explicit project root")
    sub = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}", required=True)
    create = sub.add_parser("create", help="create a v3 change artifact set")
    create.add_argument("--id", required=True); create.add_argument("--title", required=True); create.add_argument("--goal", required=True)
    create.add_argument("--context", default="No additional context."); create.add_argument("--constraint", default="No additional constraints.")
    create.add_argument("--non-goal", default="No additional non-goals."); create.add_argument("--acceptance", action="append", default=[])
    create.set_defaults(func=cmd_create)
    approve = sub.add_parser("approve", help="confirm the current contract")
    approve.add_argument("--id", required=True); approve.set_defaults(func=cmd_approve)
    status = sub.add_parser("status", help="return a compact work package")
    status.add_argument("--id", required=True); status.add_argument("--json", action="store_true"); status.set_defaults(func=cmd_status)
    record = sub.add_parser("record-check", help="record a host-executed check without running it")
    record.add_argument("--id", required=True); record.add_argument("--check-id", required=True); record.add_argument("--head", required=True)
    record.add_argument("--exit-code", required=True, type=int); record.add_argument("--summary", required=True); record.add_argument("argv", nargs=argparse.REMAINDER)
    record.set_defaults(func=cmd_record_check)
    verify = sub.add_parser("verify", help="evaluate current check evidence")
    verify.add_argument("--id", required=True); verify.add_argument("--manual", action="append", default=[])
    verify.add_argument("--review-status", choices=("PASS", "FAIL")); verify.add_argument("--review-summary", default=""); verify.add_argument("--review-cover", action="append", default=[])
    verify.set_defaults(func=cmd_verify)
    complete = sub.add_parser("complete", help="record knowledge decision after verification")
    complete.add_argument("--id", required=True); complete.add_argument("--knowledge-result", required=True, choices=sorted(KNOWLEDGE_RESULTS)); complete.add_argument("--knowledge-path", action="append", default=[])
    complete.set_defaults(func=cmd_complete)
    archive = sub.add_parser("archive", help="archive a completed v3 change")
    archive.add_argument("--id", required=True); archive.set_defaults(func=cmd_archive)
    return parser


def cmd_create(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id)
    require_attached_head(root)
    changes = root / ".dev-docs" / "changes"
    archive = changes / "archive"
    if not changes.is_dir() or not archive.is_dir():
        raise NuclioError("MISSING_SKELETON", ".dev-docs/changes and .dev-docs/changes/archive must exist")
    directory, archived = active_dir(root, change_id), archive_dir(root, change_id)
    if directory.exists() or archived.exists():
        raise NuclioError("CHANGE_EXISTS", "change ID already exists")
    if not all(isinstance(value, str) and value.strip() and "\n" not in value for value in (args.title, args.goal, args.context, args.constraint, args.non_goal)):
        raise NuclioError("INVALID_INPUT", "title and contract text must be non-empty single lines")
    acceptance = args.acceptance or [args.goal]
    if not all(isinstance(value, str) and value.strip() for value in acceptance):
        raise NuclioError("INVALID_INPUT", "acceptance items must be non-empty")
    directory.mkdir()
    frontmatter = require_yaml().safe_dump({"schema_version": 1, "change_id": change_id, "revision": 1}, sort_keys=False, allow_unicode=True).rstrip()
    criteria = "\n".join(f"- AC-{index}: {value}" for index, value in enumerate(acceptance, 1))
    (directory / "change.md").write_text(f"---\n{frontmatter}\n---\n\n# {args.title}\n\n## Goal\n\n{args.goal}\n\n## Context\n\n{args.context}\n\n## Constraints\n\n{args.constraint}\n\n## Non-goals\n\n{args.non_goal}\n\n## Acceptance Criteria\n\n{criteria}\n", encoding="utf-8")
    dump_atomic(directory / "delivery.yaml", {"schema_version": 1, "change_id": change_id, "milestones": [{"id": "M1", "kind": "delivery", "outcome": args.goal, "covers": [f"AC-{index}" for index in range(1, len(acceptance) + 1)], "status": "pending", "handoff": None}], "verification": {"checks": []}})
    dump_atomic(directory / "state.yaml", {"schema_version": 1, "change_id": change_id, "revision": None, "phase": "shape", "base_head": None, "approval_head": None, "verified_head": None, "verification": {"checks": [], "acceptance": {}, "manual": [], "review": None}, "knowledge": {"result": None, "paths": []}})
    return emit_ok({"change_id": change_id, "path": rel(root, directory), "phase": "shape"})


def cmd_approve(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); reject_v2_active(root, change_id); exact_artifacts(active_dir(root, change_id))
    change, _delivery, _checks = current_definition(root, change_id); state = load_state(root, change_id); revision = change["frontmatter"]["revision"]
    if try_recover_approval(root, change_id, state, revision):
        return emit_ok({"change_id": change_id, "approval_head": state["approval_head"], "recovered": True})
    require_clean_index(root); require_product_clean(root, change_id)
    if state.get("approval_head") and revision <= state.get("revision", 0):
        raise NuclioError("REVISION_NOT_INCREMENTED", "reapproval requires a higher change.md revision")
    original = state_file(root, change_id).read_bytes()
    state["base_head"] = state["base_head"] or head(root)
    state.update({"revision": revision, "approval_head": None, "verified_head": None, "phase": "build", "verification": {"checks": [], "acceptance": {ac: "missing" for ac in change["acceptance"]}, "manual": [], "review": None}, "knowledge": {"result": None, "paths": []}})
    paths = sorted(approval_paths(change_id)); expected_parent = head(root)
    try:
        write_state(root, change_id, state)
        git(root, "add", "--", *paths)
        git(root, "commit", "-m", approval_subject(change_id, revision))
    except Exception:
        git(root, "restore", "--staged", "--", *paths, allow_fail=True)
        state_file(root, change_id).write_bytes(original)
        raise
    if commit_parent(root) != expected_parent or commit_subject(root) != approval_subject(change_id, revision) or not approval_commit_paths(root, change_id) or not index_clean(root):
        raise NuclioError("APPROVAL_COMMIT_INVALID", "approval commit does not contain only required v3 artifacts")
    state["approval_head"] = head(root); write_state(root, change_id, state)
    return emit_ok({"change_id": change_id, "approval_head": state["approval_head"], "base_head": state["base_head"], "phase": "build"})


def cmd_status(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); change, delivery, checks = current_definition(root, change_id); state = load_state(root, change_id)
    if state.get("approval_head"):
        require_current_contract(root, change_id, state, change)
    records = {item.get("id"): item for item in state.get("verification", {}).get("checks", []) if isinstance(item, dict)}
    current = head(root)
    failed = [check["id"] for check in checks if check["id"] not in records or records[check["id"]].get("head") != current or records[check["id"]].get("exit_code") != 0 or {key: records[check["id"]].get(key) for key in ("id", "source", "run", "cwd", "timeout_seconds", "covers")} != check]
    milestone = next((item for item in delivery["milestones"] if item["status"] != "done"), delivery["milestones"][-1])
    phase = state.get("phase", "shape")
    disposition = "done" if phase == "archived" else ("await-user" if phase == "shape" else "continue")
    return emit_ok({"change_id": change_id, "phase": phase, "disposition": disposition, "goal": change["sections"]["Goal"], "constraints": change["sections"]["Constraints"], "non_goals": change["sections"]["Non-goals"], "milestone": {"id": milestone["id"], "outcome": milestone["outcome"], "acceptance": milestone["covers"]}, "handoff": milestone["handoff"], "git": {"base_head": state.get("base_head"), "approval_head": state.get("approval_head"), "current_head": current}, "failed_checks": failed, "next_action": "confirm-contract" if phase == "shape" else ("run-required-checks" if failed else "verify")})


def cmd_record_check(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); change, _delivery, checks = current_definition(root, change_id); state = load_state(root, change_id)
    require_current_contract(root, change_id, state, change); require_clean_index(root); require_product_clean(root, change_id)
    current = head(root)
    if args.head != current:
        raise NuclioError("HEAD_DRIFT", "recorded check HEAD differs from current HEAD", expected=current, actual=args.head)
    definition = next((item for item in checks if item["id"] == args.check_id), None)
    if definition is None:
        raise NuclioError("UNKNOWN_CHECK", "check ID is absent from the current definition", check_id=args.check_id)
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if argv != definition["run"]:
        raise NuclioError("CHECK_ARGV_MISMATCH", "record-check argv must exactly match the current definition", expected=definition["run"], actual=argv)
    if not isinstance(args.summary, str) or not args.summary.strip():
        raise NuclioError("INVALID_CHECK", "check summary must be non-empty")
    record = {**definition, "head": current, "exit_code": args.exit_code, "summary": args.summary.strip()[:1000]}
    verification = state.setdefault("verification", {"checks": [], "acceptance": {}, "manual": [], "review": None})
    verification["checks"] = [item for item in verification.get("checks", []) if item.get("id") != definition["id"]] + [record]
    state["verified_head"] = None; state["phase"] = "build"; write_state(root, change_id, state)
    return emit_ok({"change_id": change_id, "check_id": definition["id"], "exit_code": args.exit_code, "head": current})


def manual_records(args: argparse.Namespace, acceptance: set[str], current: str) -> list[dict[str, Any]]:
    result = []
    for item in args.manual:
        try:
            data = json.loads(item)
        except json.JSONDecodeError as exc:
            raise NuclioError("INVALID_MANUAL", "--manual must be a JSON object") from exc
        if not isinstance(data, dict) or set(data) != {"acceptance", "steps", "result", "executor"} or data["acceptance"] not in acceptance or not all(isinstance(data[key], str) and data[key].strip() for key in ("steps", "result", "executor")):
            raise NuclioError("INVALID_MANUAL", "manual observation requires acceptance, steps, result, executor")
        result.append({**data, "head": current})
    return result


def cmd_verify(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); change, _delivery, checks = current_definition(root, change_id); state = load_state(root, change_id)
    require_current_contract(root, change_id, state, change); require_clean_index(root); require_product_clean(root, change_id)
    current = head(root); verification = state.setdefault("verification", {"checks": [], "acceptance": {}, "manual": [], "review": None})
    records = {item.get("id"): item for item in verification.get("checks", []) if isinstance(item, dict)}
    passed: set[str] = set(); missing: list[str] = []
    for definition in checks:
        record = records.get(definition["id"])
        if not record or record.get("head") != current or record.get("exit_code") != 0 or {key: record.get(key) for key in ("id", "source", "run", "cwd", "timeout_seconds", "covers")} != definition:
            missing.append(definition["id"])
        elif definition["source"] == "change":
            passed.update(definition["covers"])
    manual = manual_records(args, set(change["acceptance"]), current)
    passed.update(item["acceptance"] for item in manual)
    review = verification.get("review")
    if args.review_status:
        if not args.review_summary.strip() or not args.review_cover or any(item not in change["acceptance"] for item in args.review_cover):
            raise NuclioError("INVALID_REVIEW", "review requires summary and covered Acceptance IDs")
        review = {"status": args.review_status, "summary": args.review_summary.strip()[:1000], "covers": sorted(set(args.review_cover)), "head": current}
        if args.review_status == "PASS":
            passed.update(review["covers"])
    elif isinstance(review, dict) and review.get("head") == current and review.get("status") == "PASS":
        passed.update(review.get("covers", []))
    verification["manual"], verification["review"] = manual, review
    verification["acceptance"] = {ac: "passed" if ac in passed else "missing" for ac in change["acceptance"]}
    if not missing and len(passed) == len(change["acceptance"]):
        state["verified_head"] = current; state["phase"] = "verified"
    else:
        state["verified_head"] = None; state["phase"] = "build"
    write_state(root, change_id, state)
    return emit_ok({"change_id": change_id, "verified": state["verified_head"] == current, "verified_head": state["verified_head"], "missing_checks": missing, "missing_acceptance": [ac for ac in change["acceptance"] if ac not in passed]})


def valid_knowledge_path(value: str) -> str:
    if not isinstance(value, str) or value.startswith("/") or "\\" in value or ".." in Path(value).parts or (value != ".dev-docs/index.md" and not value.startswith(".dev-docs/knowledge/")):
        raise NuclioError("INVALID_KNOWLEDGE_PATH", "knowledge paths must be .dev-docs/index.md or .dev-docs/knowledge/**")
    return value


def current_evidence(checks: list[dict[str, Any]], acceptance: list[str], verification: dict[str, Any], current: str) -> tuple[list[str], set[str]]:
    records = {item.get("id"): item for item in verification["checks"]}
    missing, passed = [], set()
    for definition in checks:
        record = records.get(definition["id"])
        if not record or record.get("head") != current or record.get("exit_code") != 0 or {key: record.get(key) for key in ("id", "source", "run", "cwd", "timeout_seconds", "covers")} != definition:
            missing.append(definition["id"])
        elif definition["source"] == "change":
            passed.update(definition["covers"])
    passed.update(item["acceptance"] for item in verification["manual"] if item["head"] == current)
    review = verification["review"]
    if isinstance(review, dict) and review["head"] == current and review["status"] == "PASS":
        passed.update(review["covers"])
    return missing, passed & set(acceptance)


def cmd_complete(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); change, _delivery, checks = current_definition(root, change_id); state = load_state(root, change_id)
    require_current_contract(root, change_id, state, change); require_clean_index(root)
    current = head(root); missing, passed = current_evidence(checks, change["acceptance"], state["verification"], current)
    if state.get("verified_head") != current or missing or passed != set(change["acceptance"]):
        raise NuclioError("VERIFICATION_NOT_CURRENT", "all current checks and Acceptance evidence must pass at the current HEAD", missing_checks=missing, missing_acceptance=sorted(set(change["acceptance"]) - passed))
    parse_change(active_dir(root, change_id) / "change.md", change_id, completion=True)
    knowledge = [valid_knowledge_path(item) for item in args.knowledge_path]
    if len(knowledge) != len(set(knowledge)) or (args.knowledge_result in {"NO_OP", "REJECTED"} and knowledge) or (args.knowledge_result in {"APPLIED", "PARTIAL"} and not knowledge):
        raise NuclioError("INVALID_KNOWLEDGE_RESULT", "knowledge result and paths are inconsistent")
    allowed = set(knowledge)
    require_product_clean(root, change_id, allowed)
    dirty_knowledge = sorted(path for path in porcelain(root) if path == ".dev-docs/index.md" or path.startswith(".dev-docs/knowledge/"))
    if sorted(knowledge) != dirty_knowledge:
        raise NuclioError("KNOWLEDGE_PATH_MISMATCH", "knowledge paths must exactly match dirty knowledge paths", expected=dirty_knowledge, actual=sorted(knowledge))
    state["knowledge"] = {"result": args.knowledge_result, "paths": knowledge}; state["phase"] = "complete"; write_state(root, change_id, state)
    return emit_ok({"change_id": change_id, "phase": "complete", "knowledge": state["knowledge"]})


def archive_subject(change_id: str) -> str:
    return f"archive({change_id}): retain complete change record"


def archive_paths(change_id: str, state: dict[str, Any]) -> list[str]:
    return [f".dev-docs/changes/{change_id}/{name}" for name in ARTIFACTS] + [f".dev-docs/changes/archive/{change_id}/{name}" for name in ARTIFACTS] + state["knowledge"]["paths"]


def validate_archive_commit(root: Path, change_id: str, state: dict[str, Any]) -> bool:
    return commit_subject(root) == archive_subject(change_id) and commit_parent(root) == state.get("verified_head") and set(changed_paths(root)) == set(archive_paths(change_id, state)) and index_clean(root)


def cmd_archive(args: argparse.Namespace, root: Path) -> int:
    change_id = validate_id(args.id); require_attached_head(root); source, target = active_dir(root, change_id), archive_dir(root, change_id)
    if target.exists() and not source.exists():
        # Do not parse unknown/old archive records. Only recognize the exact v3 terminal record requested.
        exact_artifacts(target, code="ARCHIVED_CHANGE_EXISTS")
        try:
            state = validate_state(read_yaml(target / "state.yaml", "archived state.yaml"), change_id)
        except NuclioError as exc:
            raise NuclioError("ARCHIVED_CHANGE_EXISTS", "archive target is not this v3 change") from exc
        if validate_archive_commit(root, change_id, state):
            return emit_ok({"change_id": change_id, "path": rel(root, target), "recovered": True})
        if state.get("phase") != "complete" or state.get("verified_head") != head(root):
            raise NuclioError("ARCHIVE_RECOVERY_REQUIRED", "archive move exists without a recoverable terminal state")
        parse_change(target / "change.md", change_id, completion=True)
        paths = archive_paths(change_id, state)
        require_clean_index(root); require_product_clean(root, change_id, set(paths))
        git(root, "add", "-A", "--", *paths)
        try:
            git(root, "commit", "-m", archive_subject(change_id))
        except Exception:
            git(root, "restore", "--staged", "--", *paths, allow_fail=True)
            raise NuclioError("ARCHIVE_COMMIT_FAILED", "archive move is recoverable; rerun archive")
        if not validate_archive_commit(root, change_id, state):
            raise NuclioError("ARCHIVE_COMMIT_INVALID", "archive recovery commit does not contain exactly this transition")
        return emit_ok({"change_id": change_id, "path": rel(root, target), "archive_commit": head(root), "recovered": True})
    if target.exists() or not source.exists():
        raise NuclioError("ARCHIVE_CONFLICT", "active and archive paths conflict")
    reject_v2_active(root, change_id); exact_artifacts(source); state = load_state(root, change_id); change, _delivery, _checks = current_definition(root, change_id)
    require_current_contract(root, change_id, state, change); parse_change(source / "change.md", change_id, completion=True)
    if state.get("phase") != "complete" or state.get("verified_head") != head(root):
        raise NuclioError("CHANGE_NOT_COMPLETE", "archive requires a current completed and verified change")
    require_clean_index(root); require_product_clean(root, change_id, set(state["knowledge"]["paths"]))
    target.parent.mkdir(parents=True, exist_ok=True); source.rename(target)
    paths = archive_paths(change_id, state)
    git(root, "add", "-A", "--", *paths)
    try:
        git(root, "commit", "-m", archive_subject(change_id))
    except Exception:
        git(root, "restore", "--staged", "--", *paths, allow_fail=True)
        raise NuclioError("ARCHIVE_COMMIT_FAILED", "archive move is recoverable; rerun archive")
    if not validate_archive_commit(root, change_id, state):
        raise NuclioError("ARCHIVE_COMMIT_INVALID", "archive commit does not contain exactly this transition")
    return emit_ok({"change_id": change_id, "path": rel(root, target), "archive_commit": head(root), "retained_artifacts": list(ARTIFACTS)})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, root_path(args.project_root))
    except NuclioError as error:
        return emit_error(error)
    except OSError as error:
        return emit_error(NuclioError("FILESYSTEM_ERROR", str(error)))


if __name__ == "__main__":
    raise SystemExit(main())
