import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
from typing import Any

from arthur_config import get_path


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
AUTOMATION_FILE = get_path("runtime.automationFile", str(pathlib.Path.home() / ".copilot" / "m-automations" / "automations.json"))
DEFAULT_TEMPLATE = SCRATCH / "automations.template.json"
SYNC_STATUS_FILE = SCRATCH / "arthur_automation_sync_status.json"
PRESERVE_FIELDS = {"id", "createdAt", "pinnedSessionId"}


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def automation_id(name: str) -> str:
    return "a" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:15]


def without_updated_at(value: dict[str, Any]) -> dict[str, Any]:
    comparable = copy.deepcopy(value)
    comparable.pop("updatedAt", None)
    return comparable


def read_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_name = handle.name
    pathlib.Path(temp_name).replace(path)


def normalize_automations(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("Automation file root must be a list or object")
    automations: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            automations.append(item)
    return automations


def expand_template_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("<SCRATCHPAD_PATH>", str(SCRATCH))
    if isinstance(value, list):
        return [expand_template_text(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_template_text(item) for key, item in value.items()}
    return value


def managed_fields(template: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(template)
    if existing:
        for field in PRESERVE_FIELDS:
            if field in existing:
                merged[field] = existing[field]
        merged.setdefault("id", automation_id(str(merged.get("name") or "")))
        merged.setdefault("createdAt", existing.get("createdAt") or now_iso())
        if "oneShot" in existing and "oneShot" not in merged:
            merged["oneShot"] = existing["oneShot"]
        expanded = expand_template_text(merged)
        expanded["updatedAt"] = now_iso() if without_updated_at(expanded) != without_updated_at(existing) else existing.get("updatedAt", now_iso())
        return expanded
    else:
        merged["id"] = automation_id(str(merged.get("name") or ""))
        merged["createdAt"] = now_iso()
        merged["updatedAt"] = merged["createdAt"]
        merged.setdefault("oneShot", False)
    return expand_template_text(merged)


def sync(template_path: pathlib.Path, dry_run: bool = False) -> dict[str, Any]:
    templates = normalize_automations(read_json(template_path, []))
    current = normalize_automations(read_json(AUTOMATION_FILE, []))
    by_name = {str(item.get("name")): item for item in current if item.get("name")}
    required_names = {str(item.get("name")) for item in templates if item.get("name")}
    result = {"created": [], "updated": [], "disabled": [], "unchanged": [], "template": str(template_path), "automationFile": str(AUTOMATION_FILE)}

    output = [item for item in current if not (str(item.get("name", "")).startswith("Arthur ") and str(item.get("name")) in required_names)]
    output_by_name: dict[str, dict[str, Any]] = {str(item.get("name")): item for item in output if item.get("name")}

    for template in templates:
        name = str(template.get("name") or "")
        if not name:
            continue
        existing = by_name.get(name)
        desired = managed_fields(template, existing)
        if existing is None:
            result["created"].append(name)
        elif desired != existing:
            result["updated"].append(name)
        else:
            result["unchanged"].append(name)
        output_by_name[name] = desired

    for item in current:
        name = str(item.get("name") or "")
        if not name.startswith("Arthur ") or name in required_names:
            continue
        if item.get("enabled"):
            disabled = copy.deepcopy(item)
            disabled["enabled"] = False
            output_by_name[name] = disabled
            result["disabled"].append(name)
        else:
            output_by_name[name] = item

    ordered_names = [str(item.get("name")) for item in templates if item.get("name")]
    ordered_names.extend(name for name in output_by_name if name not in ordered_names)
    synced = [output_by_name[name] for name in ordered_names if name in output_by_name]

    result["changed"] = bool(result["created"] or result["updated"] or result["disabled"])
    result["total"] = len(synced)
    if not dry_run:
        write_json_atomic(AUTOMATION_FILE, synced)
        write_json_atomic(SYNC_STATUS_FILE, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Arthur Scout automations from template.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = sync(pathlib.Path(args.template), args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
