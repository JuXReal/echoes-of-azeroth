#!/usr/bin/env python3
"""
Live Progress State Tracker (pipeline/live_state.py)
----------------------------------------------------
Single source of truth for the Web UI while the pipeline is running.

Every pipeline step reports its progress here (atomic JSON writes to
`output/qa_reports/live_state.json`, git-ignored) so the Web Studio can show
LIVE:
  - which step is currently running (1-7),
  - WHICH quest/entry is currently being validated & its attempt/status/CER,
  - counts: processed / passed / failed / retried / AI-repaired,
  - ETA (computed from the measured per-item throughput),
  - every external AI call (provider, model, entry, result).

Multiple processes (web server + pipeline steps) may write concurrently —
all writes are atomic (tmp + replace) and lock-protected.
"""

import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()

STEP_DEFS = {
    "analyze": {"index": 1, "label": "Analyse & Scraping"},
    "voices":  {"index": 2, "label": "Voice-Seed Extraktion"},
    "script":  {"index": 3, "label": "Script & Phonetik"},
    "tts":     {"index": 4, "label": "KI-Sprachsynthese"},
    "qa":      {"index": 5, "label": "Whisper-Validierung"},
    "fx":      {"index": 6, "label": "Mastering & Export"},
    "audit":   {"index": 7, "label": "Quality Audit"},
}
TOTAL_STEPS = len(STEP_DEFS)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def state_file() -> Path:
    env_path = os.environ.get("LIVE_STATE_FILE")
    if env_path:
        return Path(env_path)
    return project_root() / "output" / "qa_reports" / "live_state.json"


def _blank() -> dict:
    return {
        "job_id": None,
        "mode": None,
        "expansion": None,
        "step": None,
        "total_steps": TOTAL_STEPS,
        "started_at": None,
        "updated_at": None,
        "finished_at": None,
        "ok": None,
        "current": None,
        "counts": {
            "total": 0,
            "processed": 0,
            "passed": 0,
            "failed": 0,
            "retried": 0,
            "ai_repaired": 0,
        },
        "eta_seconds": None,
        "ai": {
            "enabled": False,
            "provider": None,
            "model": None,
            "calls": [],
        },
    }


def load() -> dict:
    try:
        with open(state_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        base = _blank()
        base.update(data)
        return base
    except Exception:
        return _blank()


def _deep_merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _write(data: dict) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)


def _compute_eta(data: dict) -> None:
    counts = data.get("counts", {})
    total = counts.get("total", 0)
    processed = counts.get("processed", 0)
    started = data.get("started_at")
    if not started or processed <= 0 or total <= processed:
        data["eta_seconds"] = None
        return
    try:
        elapsed = time.time() - float(started)
    except (TypeError, ValueError):
        data["eta_seconds"] = None
        return
    if elapsed <= 0:
        data["eta_seconds"] = None
        return
    rate = elapsed / max(1, processed)
    remaining = max(0, total - processed)
    data["eta_seconds"] = int(round(rate * remaining))


def update(**changes) -> dict:
    """Merges changes into the live state and writes it atomically."""
    with _LOCK:
        data = load()
        data = _deep_merge(data, changes)
        data["updated_at"] = time.time()
        if "counts" in changes:
            _compute_eta(data)
        _write(data)
        return data


def reset() -> dict:
    with _LOCK:
        data = _blank()
        data["updated_at"] = time.time()
        _write(data)
        return data


def begin_job(mode: str = None, expansion: str = None) -> dict:
    """Starts a fresh job (clears previous progress)."""
    with _LOCK:
        data = _blank()
        data["job_id"] = f"job-{int(time.time() * 1000)}"
        data["mode"] = mode
        data["expansion"] = expansion
        data["started_at"] = time.time()
        data["updated_at"] = time.time()
        _write(data)
        return data


def begin_step(key: str, total: int = 0, mode: str = None, expansion: str = None) -> dict:
    """Marks the start of a pipeline step and resets per-step counters."""
    with _LOCK:
        data = load()
        if not data.get("started_at"):
            data = begin_job(mode=mode, expansion=expansion)
        step_def = STEP_DEFS.get(key, {"index": 0, "label": key})
        data["step"] = {
            "key": key,
            "index": step_def["index"],
            "label": step_def["label"],
            "done": False,
            "ok": None,
        }
        data["counts"] = {
            "total": int(total),
            "processed": 0,
            "passed": 0,
            "failed": 0,
            "retried": 0,
            "ai_repaired": 0,
        }
        data["current"] = None
        data["eta_seconds"] = None
        data["finished_at"] = None
        data["ok"] = None
        data["updated_at"] = time.time()
        _write(data)
        return data


def update_current(entry: dict) -> dict:
    """Sets the entry currently being processed (no counter changes)."""
    with _LOCK:
        data = load()
        data["current"] = entry
        data["updated_at"] = time.time()
        _write(data)
        return data


def increment(
    processed: int = 0,
    passed: int = 0,
    failed: int = 0,
    retried: int = 0,
    ai_repaired: int = 0,
    current: dict = None,
) -> dict:
    """Adds to per-step counters, recomputes ETA, optionally updates current entry."""
    changes = {}
    counts = {}
    if processed:
        counts["processed"] = processed
    if passed:
        counts["passed"] = passed
    if failed:
        counts["failed"] = failed
    if retried:
        counts["retried"] = retried
    if ai_repaired:
        counts["ai_repaired"] = ai_repaired
    if counts:
        changes["counts"] = counts
    if current is not None:
        changes["current"] = current
    return update(**changes)


def finish_step(ok: bool = True) -> dict:
    with _LOCK:
        data = load()
        if data.get("step"):
            data["step"] = dict(data["step"])
            data["step"]["done"] = True
            data["step"]["ok"] = bool(ok)
        data["updated_at"] = time.time()
        _write(data)
        return data


def finish_job(ok: bool = True) -> dict:
    with _LOCK:
        data = load()
        data["finished_at"] = time.time()
        data["ok"] = bool(ok)
        data["updated_at"] = time.time()
        _write(data)
        return data


def set_ai_config(enabled: bool, provider: str = None, model: str = None) -> dict:
    with _LOCK:
        data = load()
        data["ai"]["enabled"] = bool(enabled)
        data["ai"]["provider"] = provider
        data["ai"]["model"] = model
        data["updated_at"] = time.time()
        _write(data)
        return data


def log_ai_call(provider: str, model: str, entry_id: str, note: str = "", ok: bool = True) -> dict:
    with _LOCK:
        data = load()
        data["ai"]["enabled"] = True
        data["ai"]["provider"] = provider
        data["ai"]["model"] = model
        data["ai"]["calls"].append({
            "at": time.strftime("%H:%M:%S"),
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "entry_id": entry_id,
            "note": (note or "")[:200],
            "ok": bool(ok),
        })
        data["ai"]["calls"] = data["ai"]["calls"][-50:]
        data["updated_at"] = time.time()
        _write(data)
        return data
