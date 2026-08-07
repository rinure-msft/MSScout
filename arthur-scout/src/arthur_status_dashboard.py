import argparse
import datetime as dt
import html
import json
import pathlib
import re
import subprocess
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from arthur_config import get_config, get_path


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
DEFAULT_OUTPUT = SCRATCH / "arthur_status_dashboard.html"
VERSION_FILE = SCRATCH / "arthur.version.json"
PREFLIGHT_FILE = SCRATCH / "arthur_preflight_status.json"

QUEUE_FILES = {
    "Prompt Queue": SCRATCH / "arthur_prompt_queue.jsonl",
    "Email Handoffs": SCRATCH / "arthur_email_handoff.jsonl",
    "Scout Handoffs": SCRATCH / "arthur_scout_handoff.jsonl",
}
HEARTBEAT_FILES = {
    "Voice Bridge": SCRATCH / "arthur_voice_bridge_heartbeat.json",
    "Prompt Worker": SCRATCH / "arthur_prompt_worker_heartbeat.json",
    "Edge TTS": SCRATCH / "arthur_tts_health.json",
}
LOG_FILES = [
    SCRATCH / "arthur_voice_bridge_commands.log",
    SCRATCH / "arthur_voice_bridge_stderr.log",
    SCRATCH / "arthur_prompt_worker.log",
    SCRATCH / "arthur_prompt_worker_stderr.log",
    SCRATCH / "arthur_supervisor.log",
    SCRATCH / "arthur_supervisor_stderr.log",
]
ACTIVE_STATUSES = {"pending", "running", "claimed", "blocked"}
EMAIL_HANDOFF_WARNING_SECONDS = 5 * 60
EMAIL_HANDOFF_CRITICAL_SECONDS = 10 * 60
ERROR_PATTERN = re.compile(r"\b(error|failed|exception|traceback|permissionerror|unicodeencodeerror|timeout)\b", re.I)
LOG_TIMESTAMP_PATTERN = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
EMBEDDED_ISO_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b")
EMBEDDED_LOG_PATTERN = re.compile(r"\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
WINDOWS_TIMEZONE_ALIASES = {
    "Mountain Standard Time": "America/Denver",
}


def now() -> dt.datetime:
    return dt.datetime.now(dashboard_timezone())


def system_local_timezone() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo or dashboard_timezone()


def dashboard_timezone() -> ZoneInfo:
    configured = str(get_config("timezone", "Mountain Standard Time"))
    zone_name = WINDOWS_TIMEZONE_ALIASES.get(configured, configured)
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        return dt.datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def parse_time(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=system_local_timezone())
    return parsed.astimezone(dashboard_timezone())


def age_label(value: Any) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "unknown"
    seconds = max(0, int((now() - parsed).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def human_time_label(value: Any) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "unknown"
    hour = parsed.strftime("%I").lstrip("0") or "0"
    minute = parsed.strftime("%M")
    am_pm = parsed.strftime("%p")
    tz = parsed.tzname() or parsed.strftime("%z") or "local"
    absolute = f"{parsed.strftime('%b')} {parsed.day}, {parsed.year} {hour}:{minute} {am_pm} {tz}"
    return f"{absolute} ({age_label(value)})"


def human_time_absolute(value: Any) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return str(value)
    hour = parsed.strftime("%I").lstrip("0") or "0"
    minute = parsed.strftime("%M")
    am_pm = parsed.strftime("%p")
    tz = parsed.tzname() or parsed.strftime("%z") or "local"
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year} {hour}:{minute} {am_pm} {tz}"


def humanize_embedded_timestamps(text: Any) -> str:
    value = str(text or "")
    value = EMBEDDED_ISO_PATTERN.sub(lambda match: human_time_absolute(match.group(0)), value)
    value = EMBEDDED_LOG_PATTERN.sub(lambda match: f"[{human_time_absolute(match.group('timestamp'))}]", value)
    return value


def age_seconds(value: Any) -> int | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return max(0, int((now() - parsed).total_seconds()))


def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def read_jsonl(path: pathlib.Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    items: list[dict[str, Any]] = []
    invalid = 0
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(data, dict):
            items.append(data)
    return items, invalid


def truncate(text: Any, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", humanize_embedded_timestamps(text)).strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def count_statuses(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def email_sla(item: dict[str, Any]) -> tuple[str, str]:
    if str(item.get("status") or "") != "pending":
        return "success", "met"
    created = item.get("created_at") or item.get("timestamp")
    seconds = age_seconds(created)
    if seconds is None:
        return "warning", "unknown age"
    if seconds >= EMAIL_HANDOFF_CRITICAL_SECONDS:
        return "danger", f"critical: {seconds // 60}m pending"
    if seconds >= EMAIL_HANDOFF_WARNING_SECONDS:
        return "warning", f"warning: {seconds // 60}m pending"
    return "success", f"ok: {seconds // 60}m pending"


def queue_item_sla(queue_name: str, item: dict[str, Any]) -> tuple[str, str]:
    if queue_name == "Email Handoffs":
        return email_sla(item)
    return "neutral", "n/a"


def recent_items(items: list[dict[str, Any]], queue_name: str, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items[-limit:]:
        created = item.get("created_at") or item.get("timestamp") or item.get("sent_at") or item.get("completed_at")
        sla_status, sla_label = queue_item_sla(queue_name, item)
        rows.append(
            {
                "id": truncate(item.get("id") or item.get("prompt_id") or "", 48),
                "status": str(item.get("status") or ""),
                "type": truncate(item.get("type") or item.get("handler") or "", 32),
                "age": human_time_label(created),
                "sla_status": sla_status,
                "sla": sla_label,
                "subject": truncate(item.get("subject") or item.get("prompt") or item.get("source_prompt") or item.get("response") or "", 120),
            }
        )
    return rows


def pid_running(pid: Any) -> bool | None:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return None
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"if (Get-Process -Id {value} -ErrorAction SilentlyContinue) {{ 'yes' }}"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip() == "yes"


def health_status(heartbeat: dict[str, Any] | None, stale_seconds: int = 180) -> tuple[str, str]:
    if heartbeat is None:
        return "danger", "Missing heartbeat"
    timestamp = heartbeat.get("timestamp")
    parsed = parse_time(timestamp)
    if parsed is None:
        return "warning", "Heartbeat timestamp unreadable"
    seconds = (now() - parsed).total_seconds()
    running = pid_running(heartbeat.get("pid"))
    if running is False:
        return "danger", "Process is not running"
    if seconds > stale_seconds:
        return "warning", f"Heartbeat stale: {age_label(timestamp)}"
    status = str(heartbeat.get("status") or "unknown")
    if status == "healthy":
        return "success", status
    if status in {"unhealthy", "failed"}:
        return "danger", status
    if status == "recovered":
        return "warning", status
    if status in {"listening", "idle"}:
        return "success", status
    if status in {"speaking", "running"}:
        return "warning", status
    return "warning", status


def collect_health() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, path in HEARTBEAT_FILES.items():
        heartbeat = read_json(path)
        severity, status = health_status(heartbeat, stale_seconds=900 if name == "Edge TTS" else 180)
        rows.append(
            {
                "name": name,
                "severity": severity,
                "status": status,
                "pid": str((heartbeat or {}).get("pid") or "unknown"),
                "updated": human_time_label((heartbeat or {}).get("timestamp")),
                "message": truncate((heartbeat or {}).get("message") or (heartbeat or {}).get("error") or (heartbeat or {}).get("reason") or (heartbeat or {}).get("mic_name") or "", 120),
            }
        )
    return rows


def collect_queues() -> list[dict[str, Any]]:
    queues: list[dict[str, Any]] = []
    for name, path in QUEUE_FILES.items():
        items, invalid = read_jsonl(path)
        active = [item for item in items if str(item.get("status") or "") in ACTIVE_STATUSES]
        counts = count_statuses(items)
        sla_alerts: list[dict[str, str]] = []
        if name == "Email Handoffs":
            for item in active:
                sla_status, sla_label = email_sla(item)
                if sla_status in {"warning", "danger"}:
                    sla_alerts.append(
                        {
                            "severity": sla_status,
                            "id": truncate(item.get("id") or item.get("prompt_id") or "", 64),
                            "subject": truncate(item.get("subject") or item.get("source_prompt") or "", 140),
                            "sla": sla_label,
                        }
                    )
        severity = "success"
        if any(str(item.get("status") or "") == "blocked" for item in active):
            severity = "danger"
        elif any(alert["severity"] == "danger" for alert in sla_alerts):
            severity = "danger"
        elif any(alert["severity"] == "warning" for alert in sla_alerts):
            severity = "warning"
        elif active:
            severity = "warning"
        queues.append(
            {
                "name": name,
                "severity": severity,
                "total": len(items),
                "active": len(active),
                "invalid": invalid,
                "counts": counts,
                "sla_alerts": sla_alerts,
                "recent": recent_items(items, name),
                "active_items": recent_items(active, name, 6),
            }
        )
    return queues


def read_recent_lines(path: pathlib.Path, limit: int = 500) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def line_timestamp(line: str) -> dt.datetime | None:
    match = LOG_TIMESTAMP_PATTERN.match(line)
    if not match:
        return None
    return parse_time(match.group("timestamp"))


def latest_supervisor_start() -> dt.datetime | None:
    supervisor_log = SCRATCH / "arthur_supervisor.log"
    latest: dt.datetime | None = None
    for line in read_recent_lines(supervisor_log, 2000):
        if "Arthur supervisor started." not in line:
            continue
        timestamp = line_timestamp(line)
        if timestamp is not None:
            latest = timestamp
    return latest


def collect_errors() -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    since = latest_supervisor_start()
    for path in LOG_FILES:
        for line in read_recent_lines(path):
            timestamp = line_timestamp(line)
            if since is not None and timestamp is not None and timestamp < since:
                continue
            if ERROR_PATTERN.search(line):
                errors.append({"source": path.name, "line": truncate(humanize_embedded_timestamps(line), 220)})
    return errors[-12:]


def collect_last_spoken_response() -> str:
    commands = SCRATCH / "arthur_voice_bridge_commands.log"
    for line in reversed(read_recent_lines(commands, 1000)):
        marker = "Spoke response using "
        if marker not in line:
            continue
        _, _, response = line.partition(": ")
        return truncate(response, 260)
    return "No spoken response found."


def collect_version() -> dict[str, Any]:
    version = read_json(VERSION_FILE) or {}
    checksums = version.get("checksums") if isinstance(version.get("checksums"), dict) else {}
    return {
        "packageVersion": str(version.get("packageVersion") or "unknown"),
        "commitSha": str(version.get("commitSha") or "unknown"),
        "installTime": human_time_label(version.get("installTime")),
        "generatedAt": human_time_label(version.get("generatedAt")),
        "scratchpadPath": str(version.get("scratchpadPath") or SCRATCH),
        "checksums": checksums,
    }


def collect_preflight() -> dict[str, Any]:
    preflight = read_json(PREFLIGHT_FILE) or {}
    checks = preflight.get("checks") if isinstance(preflight.get("checks"), list) else []
    return {
        "status": str(preflight.get("status") or "unknown"),
        "failed": int(preflight.get("failed") or 0),
        "warnings": int(preflight.get("warnings") or 0),
        "strict": bool(preflight.get("strict")),
        "checks": [item for item in checks if isinstance(item, dict)],
    }


def status_summary(queues: list[dict[str, Any]], health: list[dict[str, str]], errors: list[dict[str, str]]) -> tuple[str, str]:
    active = sum(int(queue["active"]) for queue in queues)
    sla_alerts = sum(len(queue.get("sla_alerts", [])) for queue in queues)
    danger = any(row["severity"] == "danger" for row in health) or any(queue["severity"] == "danger" for queue in queues)
    warning = any(row["severity"] == "warning" for row in health) or any(queue["severity"] == "warning" for queue in queues)
    if danger:
        return "danger", f"Needs attention: {active} active queue item(s), {sla_alerts} SLA alert(s), {len(errors)} recent error(s)."
    if warning:
        return "warning", f"Running with warnings: {active} active queue item(s), {sla_alerts} SLA alert(s), {len(errors)} recent error(s)."
    return "success", f"Healthy: {active} active queue item(s), {sla_alerts} SLA alert(s), {len(errors)} recent error(s)."


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def badge(status: str, label: str) -> str:
    return f'<span class="badge badge-{esc(status)}">{esc(label)}</span>'


def render_counts(counts: dict[str, int]) -> str:
    if not counts:
        return '<span class="muted">none</span>'
    return " ".join(badge("neutral", f"{key}: {value}") for key, value in sorted(counts.items()))


def render_rows(rows: list[dict[str, str]]) -> str:
    if not rows:
        return '<tr><td colspan="6" class="muted">No items.</td></tr>'
    html_rows = []
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td><code>{esc(row['id'])}</code></td>"
            f"<td>{badge(row['status'] or 'neutral', row['status'] or 'unknown')}</td>"
            f"<td>{esc(row['type'])}</td>"
            f"<td>{esc(row['age'])}</td>"
            f"<td>{badge(row['sla_status'], row['sla'])}</td>"
            f"<td>{esc(row['subject'])}</td>"
            "</tr>"
        )
    return "\n".join(html_rows)


def build_html() -> str:
    queues = collect_queues()
    health = collect_health()
    errors = collect_errors()
    last_spoken = collect_last_spoken_response()
    version = collect_version()
    preflight = collect_preflight()
    severity, summary = status_summary(queues, health, errors)
    generated_at = human_time_label(now().isoformat())
    checksum_rows = "\n".join(
        f"<tr><td>{esc(name)}</td><td><code>{esc(str(value)[:16])}…</code></td></tr>"
        for name, value in sorted(version["checksums"].items())
    ) or '<tr><td colspan="2" class="muted">No checksums found.</td></tr>'

    queue_cards = []
    for queue in queues:
        active_table = ""
        if queue["active_items"]:
            active_table = (
                '<h3>Active items</h3><table><thead><tr><th>ID</th><th>Status</th><th>Type</th><th>Time</th><th>SLA</th><th>Summary</th></tr></thead>'
                f"<tbody>{render_rows(queue['active_items'])}</tbody></table>"
            )
        sla_alerts = ""
        if queue["sla_alerts"]:
            alerts = "".join(
                f"<li>{badge(alert['severity'], alert['sla'])} <code>{esc(alert['id'])}</code> {esc(alert['subject'])}</li>"
                for alert in queue["sla_alerts"]
            )
            sla_alerts = f'<div class="sla-alerts"><h3>Email handoff SLA alerts</h3><ul>{alerts}</ul></div>'
        queue_cards.append(
            f"""
            <section class="card">
              <div class="card-title">
                <h2>{esc(queue['name'])}</h2>
                {badge(queue['severity'], f"{queue['active']} active")}
              </div>
              <div class="metrics">
                <div><strong>{queue['total']}</strong><span>Total</span></div>
                <div><strong>{queue['active']}</strong><span>Active</span></div>
                <div><strong>{queue['invalid']}</strong><span>Invalid JSONL</span></div>
              </div>
              <div class="counts">{render_counts(queue['counts'])}</div>
              {sla_alerts}
              {active_table}
              <h3>Recent items</h3>
              <table><thead><tr><th>ID</th><th>Status</th><th>Type</th><th>Time</th><th>SLA</th><th>Summary</th></tr></thead><tbody>{render_rows(queue['recent'])}</tbody></table>
            </section>
            """
        )

    health_rows = "\n".join(
        f"<tr><td>{esc(row['name'])}</td><td>{badge(row['severity'], row['status'])}</td><td><code>{esc(row['pid'])}</code></td><td>{esc(row['updated'])}</td><td>{esc(row['message'])}</td></tr>"
        for row in health
    )
    error_rows = "\n".join(
        f"<tr><td>{esc(row['source'])}</td><td>{esc(row['line'])}</td></tr>" for row in errors
    ) or '<tr><td colspan="2" class="muted">No recent errors found.</td></tr>'
    preflight_rows = "\n".join(
        f"<tr><td>{esc(item.get('name', 'unknown'))}</td><td>{badge('success' if item.get('ok') else item.get('severity', 'danger'), 'passed' if item.get('ok') else item.get('severity', 'failed'))}</td><td>{esc(item.get('detail', ''))}</td></tr>"
        for item in preflight["checks"]
    ) or '<tr><td colspan="3" class="muted">No preflight status found.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arthur Status Dashboard</title>
<script>
  (() => {{
    const param = new URLSearchParams(window.location.search).get("scoutTheme");
    const theme =
      param || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  }})();
</script>
<style>
:root {{
  color-scheme: light;
  --cp-bg: #f7f4ef;
  --cp-bg-elevated: #fcfbf8;
  --cp-surface: #ffffff;
  --cp-surface-soft: #f5f5f5;
  --cp-border: #dedede;
  --cp-border-strong: #919191;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-text-soft: #6f6f6f;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-soft: rgba(177, 31, 75, 0.08);
  --cp-accent-fg: #ffffff;
  --cp-success: #16a34a;
  --cp-danger: #dc2626;
  --cp-warning: #f59e0b;
  --cp-link: #0078d4;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
  --cp-overlay: rgba(255, 255, 255, 0.8);
  --cp-panel: rgba(255, 255, 255, 0.86);
  --cp-panel-strong: rgba(255, 255, 255, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.55);
  --cp-highlight: rgba(177, 31, 75, 0.12);
}}
html[data-theme="dark"] {{
  color-scheme: dark;
  --cp-bg: #3d3b3a;
  --cp-bg-elevated: #343231;
  --cp-surface: #292929;
  --cp-surface-soft: #2e2e2e;
  --cp-border: #474747;
  --cp-border-strong: #5f5f5f;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-text-soft: #b0b0b0;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-soft: rgba(253, 142, 161, 0.14);
  --cp-accent-fg: #1a1a1a;
  --cp-success: #4ade80;
  --cp-danger: #f87171;
  --cp-warning: #fbbf24;
  --cp-link: #4da6ff;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  --cp-overlay: rgba(41, 41, 41, 0.88);
  --cp-panel: rgba(41, 41, 41, 0.72);
  --cp-panel-strong: rgba(41, 41, 41, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.04);
  --cp-highlight: rgba(253, 142, 161, 0.12);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--cp-bg);
  color: var(--cp-text);
  font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
}}
main {{ max-width: 1280px; margin: 0 auto; padding: 32px; }}
.hero {{
  background: var(--cp-bg-elevated);
  border: 1px solid var(--cp-border);
  border-radius: 16px;
  box-shadow: var(--cp-shadow);
  padding: 24px;
  margin-bottom: 20px;
}}
.hero-top, .card-title {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }}
.brand-lockup {{ display: flex; align-items: center; gap: 12px; }}
.brand-mark {{ flex: 0 0 auto; width: 32px; height: 32px; }}
h1, h2, h3, p {{ margin-top: 0; }}
h1 {{ font-size: 32px; margin-bottom: 8px; }}
h2 {{ font-size: 20px; margin-bottom: 8px; }}
h3 {{ font-size: 14px; color: var(--cp-text-muted); margin: 16px 0 8px; text-transform: uppercase; letter-spacing: 0.04em; }}
.muted {{ color: var(--cp-text-muted); }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }}
.card {{
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 16px;
  box-shadow: 0 0 2px var(--cp-border), 0 1px 2px var(--cp-border);
  padding: 20px;
  overflow: hidden;
}}
.wide {{ grid-column: 1 / -1; }}
.metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 16px 0; }}
.metrics div {{ background: var(--cp-surface-soft); border: 1px solid var(--cp-border); border-radius: 0.625rem; padding: 12px; }}
.metrics strong {{ display: block; font-size: 24px; }}
.metrics span {{ color: var(--cp-text-muted); font-size: 12px; }}
.badge {{ display: inline-flex; align-items: center; border-radius: 0.625rem; padding: 4px 8px; font-size: 12px; border: 1px solid var(--cp-border); background: var(--cp-surface-soft); color: var(--cp-text); }}
.badge-success {{ color: var(--cp-success); border-color: var(--cp-success); }}
.badge-warning {{ color: var(--cp-warning); border-color: var(--cp-warning); }}
.badge-danger {{ color: var(--cp-danger); border-color: var(--cp-danger); }}
.badge-neutral {{ color: var(--cp-text-muted); }}
.badge-pending, .badge-running, .badge-claimed {{ color: var(--cp-warning); border-color: var(--cp-warning); }}
.badge-blocked, .badge-failed {{ color: var(--cp-danger); border-color: var(--cp-danger); }}
.badge-completed, .badge-sent {{ color: var(--cp-success); border-color: var(--cp-success); }}
.counts {{ display: flex; flex-wrap: wrap; gap: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border-bottom: 1px solid var(--cp-border); padding: 8px; text-align: left; vertical-align: top; }}
th {{ color: var(--cp-text-muted); font-weight: 600; }}
code {{ font-family: Consolas, "Courier New", Courier, monospace; color: var(--cp-text-soft); }}
.last-spoken {{ background: var(--cp-accent-soft); border: 1px solid var(--cp-border); border-radius: 0.625rem; padding: 12px; }}
.version-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 16px 0; }}
.version-grid div {{ background: var(--cp-surface-soft); border: 1px solid var(--cp-border); border-radius: 0.625rem; padding: 12px; }}
.version-grid span {{ display: block; color: var(--cp-text-muted); font-size: 12px; margin-bottom: 4px; }}
.version-grid strong {{ display: block; overflow-wrap: anywhere; }}
.preflight-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 16px 0; }}
.preflight-grid div {{ background: var(--cp-surface-soft); border: 1px solid var(--cp-border); border-radius: 0.625rem; padding: 12px; }}
.preflight-grid span {{ display: block; color: var(--cp-text-muted); font-size: 12px; margin-bottom: 4px; }}
.preflight-grid strong {{ display: block; overflow-wrap: anywhere; }}
.sla-alerts {{ margin-top: 16px; background: var(--cp-accent-soft); border: 1px solid var(--cp-border); border-radius: 0.625rem; padding: 12px; }}
.sla-alerts ul {{ margin: 0; padding-left: 20px; }}
.sla-alerts li {{ margin: 6px 0; }}
.actions {{ margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; }}
button {{ border: 1px solid var(--cp-accent); background: var(--cp-accent); color: var(--cp-accent-fg); border-radius: 0.625rem; padding: 8px 12px; font: inherit; cursor: pointer; }}
button:hover {{ background: var(--cp-accent-hover); }}
@media (max-width: 900px) {{ main {{ padding: 16px; }} .grid, .version-grid, .preflight-grid {{ grid-template-columns: 1fr; }} .hero-top, .card-title {{ flex-direction: column; }} }}
</style>
</head>
<body>
<main>
  <section class="hero">
    <div class="hero-top">
      <div class="brand-lockup">
        <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="arthur-mark-gradient" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop stop-color="#fd8ea1"/><stop offset="1" stop-color="#b11f4b"/></linearGradient></defs><circle cx="16" cy="16" r="11" fill="none" stroke="url(#arthur-mark-gradient)" stroke-width="5"/></svg>
        <div>
        <h1>Arthur Status Dashboard</h1>
        <p class="muted">Generated {esc(generated_at)} from live Arthur files in <code>{esc(SCRATCH)}</code>.</p>
        </div>
      </div>
      {badge(severity, summary)}
    </div>
    <div class="actions"><button onclick="window.location.reload()">Refresh snapshot</button></div>
  </section>
  <section class="grid">
    <section class="card">
      <div class="card-title"><h2>Worker Health</h2>{badge("neutral", "live heartbeat")}</div>
      <table><thead><tr><th>Component</th><th>Status</th><th>PID</th><th>Updated</th><th>Message</th></tr></thead><tbody>{health_rows}</tbody></table>
    </section>
    <section class="card">
      <div class="card-title"><h2>Last Spoken Response</h2>{badge("neutral", "voice")}</div>
      <div class="last-spoken">{esc(last_spoken)}</div>
    </section>
    <section class="card wide">
      <div class="card-title"><h2>Deployment Version</h2>{badge("neutral", f"{len(version['checksums'])} checksums")}</div>
      <div class="version-grid">
        <div><span>Package Version</span><strong>{esc(version['packageVersion'])}</strong></div>
        <div><span>Commit SHA</span><strong><code>{esc(version['commitSha'])}</code></strong></div>
        <div><span>Install Time</span><strong>{esc(version['installTime'])}</strong></div>
        <div><span>Manifest Updated</span><strong>{esc(version['generatedAt'])}</strong></div>
      </div>
      <h3>Live file checksums</h3>
      <table><thead><tr><th>File</th><th>SHA-256</th></tr></thead><tbody>{checksum_rows}</tbody></table>
    </section>
    <section class="card wide">
      <div class="card-title"><h2>Install / Update Preflight</h2>{badge("success" if preflight['status'] == "passed" else "danger", preflight['status'])}</div>
      <div class="preflight-grid">
        <div><span>Mode</span><strong>{"strict" if preflight['strict'] else "install/update"}</strong></div>
        <div><span>Failures</span><strong>{esc(preflight['failed'])}</strong></div>
        <div><span>Warnings</span><strong>{esc(preflight['warnings'])}</strong></div>
      </div>
      <table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{preflight_rows}</tbody></table>
    </section>
    {''.join(queue_cards)}
    <section class="card wide">
      <div class="card-title"><h2>Last Errors</h2>{badge("neutral", f"{len(errors)} recent")}</div>
      <table><thead><tr><th>Source</th><th>Log line</th></tr></thead><tbody>{error_rows}</tbody></table>
    </section>
  </section>
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Arthur status dashboard HTML snapshot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output HTML path.")
    args = parser.parse_args()
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
