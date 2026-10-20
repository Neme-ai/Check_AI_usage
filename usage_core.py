"""Conservative, credential-free usage normalization and local cache."""
from __future__ import annotations
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

PROVIDERS = {
    "codex": {"name": "Codex / Work", "plan": "Plus", "url": "https://chatgpt.com/settings/usage?tab=overview", "host": "chatgpt.com"},
    "claude": {"name": "Claude", "plan": "Pro", "url": "https://claude.ai/settings/usage", "host": "claude.ai"},
}

def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 100 else None

def timestamp(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
            result = dt.timestamp()
        else:
            return None
        # Reject milliseconds accidentally supplied as seconds and corrupt cache dates.
        return result if math.isfinite(result) and 0 < result < 4133980800 else None
    except (ValueError, OverflowError):
        return None

def window(key, label, used, reset=None, seconds=None):
    used = percent(used)
    if used is None:
        return None
    return {"key": key, "label": label, "used": used, "remaining": round(100-used, 2),
            "reset_at": timestamp(reset), "seconds": seconds}

def period_label(seconds, fallback):
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        if seconds == 604800:
            return "每周"
        if seconds == 18000:
            return "5 小时"
        if seconds > 0:
            return f"{seconds / 3600:g} 小时"
    return fallback

def parse_codex(payload):
    if not isinstance(payload, dict):
        return []
    result = []
    def add_group(group, prefix="", name=""):
        if not isinstance(group, dict):
            return
        for key, fallback in (("primary_window", "主额度"), ("secondary_window", "次额度")):
            raw = group.get(key)
            if not isinstance(raw, dict):
                continue
            seconds = raw.get("limit_window_seconds")
            item = window(prefix+key, name+period_label(seconds, fallback), raw.get("used_percent"), raw.get("reset_at"), seconds)
            if item:
                result.append(item)
    add_group(payload.get("rate_limit"))
    additional = payload.get("additional_rate_limits")
    if isinstance(additional, list):
        for i, group in enumerate(additional):
            if isinstance(group, dict):
                name = str(group.get("limit_name") or group.get("metered_feature") or "其他额度")[:60]
                add_group(group.get("rate_limit"), f"additional_{i}_", name+" · ")
    add_group(payload.get("code_review_rate_limit"), "review_", "代码审查 · ")
    return result

def parse_claude(payload):
    if not isinstance(payload, dict):
        return []
    labels = {"five_hour": ("5 小时", 18000), "seven_day": ("每周 · 全部模型", 604800),
              "seven_day_sonnet": ("每周 · Sonnet", 604800), "seven_day_opus": ("每周 · Opus", 604800),
              "seven_day_oauth_apps": ("每周 · OAuth 应用", 604800), "seven_day_cowork": ("每周 · Cowork", 604800)}
    result = []
    for key, raw in payload.items():
        if key not in labels or not isinstance(raw, dict):
            continue
        label, seconds = labels[key]
        item = window(key, label, raw.get("utilization"), raw.get("resets_at"), seconds)
        if item:
            result.append(item)
    return result

def parse_payload(provider, payload):
    return (parse_codex if provider == "codex" else parse_claude)(payload)

def empty_state():
    return {key: {"windows": [], "updated_at": None, "status": "未登录", "source": ""} for key in PROVIDERS}

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def load_cache(path):
    result = empty_state()
    raw = read_json(path, {})
    if not isinstance(raw, dict):
        return result
    for key in result:
        item = raw.get(key)
        if not isinstance(item, dict) or not isinstance(item.get("windows"), list):
            continue
        windows = []
        for w in item["windows"]:
            if not isinstance(w, dict):
                continue
            parsed = window(str(w.get("key", "")), str(w.get("label", "额度")), w.get("used"), w.get("reset_at"), w.get("seconds"))
            if parsed:
                parsed["reset_text"] = str(w.get("reset_text", ""))[:160]
                windows.append(parsed)
        if windows:
            result[key] = {"windows": windows, "updated_at": timestamp(item.get("updated_at")), "status": "缓存 · 待刷新", "source": "缓存"}
    return result

def is_stale(state, now=None):
    now = time.time() if now is None else now
    updated = state.get("updated_at")
    return state.get("status") != "正常" or not updated or now-updated > 150 or any(w.get("reset_at") and w["reset_at"] <= now for w in state.get("windows", []))

def countdown(reset_at, now=None):
    if not reset_at:
        return "重置时间未提供"
    seconds = reset_at - (time.time() if now is None else now)
    if seconds <= 0:
        return "已到重置时间 · 待刷新"
    minutes = math.ceil(seconds/60)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    return (f"{days}天 " if days else "") + f"{hours}小时 {mins}分后重置"
