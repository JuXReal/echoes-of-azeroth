#!/usr/bin/env python3
"""
Unified Frontier-AI Client (pipeline/ai_client.py)
--------------------------------------------------
Single gateway for AI repair / optimization calls to external providers:

    - OpenAI        (api.openai.com)
    - OpenRouter    (openrouter.ai)
    - Google Gemini (generativelanguage.googleapis.com)
    - DeepSeek      (api.deepseek.com)
    - Ollama        (local, http://127.0.0.1:11434)
    - none          (disable external AI — deterministic local repair only)

SECURITY / SECRET HANDLING
--------------------------
API keys are read EXCLUSIVELY from the environment (.env — git-ignored).
Keys are NEVER written to config.yaml, JSON reports, the live state or any
web API response. The web settings UI only receives a boolean "api_key_set".
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

PROVIDERS = {
    "none":       {"label": "Keine externe KI (nur lokale Regeln)", "base_url": "",                                              "default_model": ""},
    "openai":     {"label": "OpenAI",                             "base_url": "https://api.openai.com/v1",                       "default_model": "gpt-4o"},
    "openrouter": {"label": "OpenRouter",                         "base_url": "https://openrouter.ai/api/v1",                    "default_model": "anthropic/claude-3.5-sonnet"},
    "google":     {"label": "Google Gemini",                      "base_url": "https://generativelanguage.googleapis.com/v1beta", "default_model": "gemini-2.0-flash"},
    "deepseek":   {"label": "DeepSeek",                           "base_url": "https://api.deepseek.com/v1",                     "default_model": "deepseek-chat"},
    "ollama":     {"label": "Lokales Ollama",                     "base_url": "http://127.0.0.1:11434",                          "default_model": "qwen2.5:7b"},
}

REPAIR_SYSTEM_PROMPT = (
    "Du bist der \"Frontier QA Inspector\" einer World-of-Warcraft-Voiceover-Pipeline "
    "(Coqui XTTS-v2, deutsche Sprache). Ein gesprochener Take wurde mit Faster-Whisper "
    "transkribiert und weicht vom Zieltext ab. Erstelle daraus eine optimierte, phonetisch "
    "robuste deutsche TTS-Vorlage:\n"
    "- Warcraft-Eigennamen lautgetreu eingedeutscht und ohne Apostrophe schreiben "
    "(z. B. \"Xal'atath\" -> \"Xallatath\", \"Lor'themar\" -> \"Lorthemar\").\n"
    "- Lange Komposita mit Leerzeichen trennen (z. B. \"Zwielichtklingenkultisten\" -> "
    "\"Zwielichtklingen Kultisten\").\n"
    "- Kurze, klare Sätze mit natürlichen Atempausen durch Kommas und Punkte; keine "
    "Semikolons, keine Doppelpunkte.\n"
    "- Keine Anführungszeichen und keine ALL-CAPS-Wörter verwenden.\n"
    "Antworte NUR mit der fertigen TTS-Vorlage als Fließtext, ohne Kommentare, ohne Markdown."
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_env(env_file: Optional[Path] = None) -> None:
    """Loads .env into os.environ without overwriting already-set variables."""
    env_file = env_file or (project_root() / ".env")
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def get_settings(cfg: Optional[Dict] = None) -> Dict:
    """Resolves the active AI settings from .env + config.yaml (no secrets in config!)."""
    load_env()
    ai_cfg = (cfg or {}).get("ai", {})

    provider = (os.getenv("AI_PROVIDER") or ai_cfg.get("provider") or "none").strip().lower()
    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = (
        os.getenv("AI_BASE_URL")
        or ai_cfg.get("base_url")
        or PROVIDERS.get(provider, {}).get("base_url", "")
    ).rstrip("/")
    model = os.getenv("AI_MODEL") or ai_cfg.get("model") or PROVIDERS.get(provider, {}).get("default_model", "")

    enabled = ai_cfg.get("enabled", True)
    env_enabled = os.getenv("AI_ENABLED")
    if env_enabled is not None:
        enabled = env_enabled.strip().lower() in ("1", "true", "yes", "on")

    # Backwards-compatible fallback for the legacy .env keys
    if provider == "none" or not api_key:
        if os.getenv("OPENAI_API_KEY"):
            provider, api_key = "openai", os.getenv("OPENAI_API_KEY", "").strip()
            base_url = base_url or "https://api.openai.com/v1"
            model = model or "gpt-4o"
        elif os.getenv("GEMINI_API_KEY"):
            provider, api_key = "google", os.getenv("GEMINI_API_KEY", "").strip()
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
            model = model or "gemini-2.0-flash"

    if provider == "ollama":
        base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    if provider not in PROVIDERS:
        provider = "none"

    try:
        trigger = int(os.getenv("AI_REPAIR_AFTER_FAILURES") or ai_cfg.get("trigger_after_failures", 3))
    except (TypeError, ValueError):
        trigger = 3

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "enabled": bool(enabled),
        "trigger_after_failures": max(1, trigger),
        "temperature": float(ai_cfg.get("temperature", 0.3)),
        "timeout_sec": int(ai_cfg.get("timeout_sec", 45)),
        "max_tokens": int(ai_cfg.get("max_tokens", 1500)),
    }


def is_available(settings: Dict) -> bool:
    if not settings.get("enabled") or settings.get("provider") in (None, "none"):
        return False
    if settings.get("provider") == "ollama":
        return bool(settings.get("base_url"))
    return bool(settings.get("api_key"))


def _chat_openai_compatible(messages: List[Dict], s: Dict, temperature: float, timeout: int, max_tokens: int) -> str:
    resp = requests.post(
        f"{s['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {s['api_key']}", "Content-Type": "application/json"},
        json={
            "model": s["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _chat_google(messages: List[Dict], s: Dict, temperature: float, timeout: int, max_tokens: int) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    text = f"{system}\n\n{user}" if system else user
    resp = requests.post(
        f"{s['base_url']}/models/{s['model']}:generateContent",
        params={"key": s["api_key"]},
        json={
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _chat_ollama(messages: List[Dict], s: Dict, temperature: float, timeout: int) -> str:
    resp = requests.post(
        f"{s['base_url']}/api/chat",
        json={"model": s["model"], "messages": messages, "stream": False,
              "options": {"temperature": temperature}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def chat(
    messages: List[Dict],
    settings: Dict,
    temperature: Optional[float] = None,
    timeout: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Sends a chat request to the configured provider. Raises on failure."""
    provider = settings.get("provider")
    if provider in (None, "none"):
        raise RuntimeError("No AI provider configured")
    temp = settings.get("temperature", 0.3) if temperature is None else temperature
    t_out = timeout or settings.get("timeout_sec", 45)
    t_max = max_tokens or settings.get("max_tokens", 1500)

    if provider == "google":
        return _chat_google(messages, settings, temp, t_out, t_max)
    if provider == "ollama" and "/v1" not in (settings.get("base_url") or ""):
        return _chat_ollama(messages, settings, temp, t_out)
    return _chat_openai_compatible(messages, settings, temp, t_out, t_max)


def test_connection(settings: Dict) -> Tuple[bool, str]:
    """Checks the configured AI connection with a minimal ping request."""
    if not settings.get("enabled"):
        return False, "KI-Reparatur ist deaktiviert."
    if not is_available(settings):
        if settings.get("provider") in (None, "none"):
            return False, "Kein KI-Provider ausgewählt."
        return False, "API-Key fehlt (oder Base-URL leer bei Ollama)."
    try:
        reply = chat(
            [{"role": "system", "content": "Antworte exakt mit: OK"},
             {"role": "user", "content": "Ping"}],
            settings, temperature=0, timeout=15, max_tokens=8,
        )
        if reply and reply.strip():
            return True, f"Verbindung OK — Antwort: {reply.strip()[:60]}"
        return False, "Leere Antwort vom Provider erhalten."
    except Exception as e:
        return False, f"Verbindungsfehler: {e}"


def repair_script_with_ai(
    settings: Dict,
    target_text: str,
    transcript: str,
    entry_context: str = "",
) -> Tuple[Optional[str], str]:
    """
    Frontier QA Inspector: lets the configured AI rewrite the failed line into a
    phonetically robust German TTS script. Returns (repaired_text, note).
    Returns (None, reason) when the call fails or the reply is unusable.
    """
    if not is_available(settings):
        return None, "ai_disabled"
    user = f"Zieltext:\n{target_text}\n\nWhisper-Transkript (fehlerhafter Take):\n{transcript}"
    if entry_context:
        user = f"Kontext: {entry_context}\n\n" + user
    try:
        raw = chat(
            [{"role": "system", "content": REPAIR_SYSTEM_PROMPT},
             {"role": "user", "content": user}],
            settings,
        )
    except Exception as e:
        return None, f"call_failed: {e}"

    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw or "").strip().strip("`").strip()
    if not cleaned:
        return None, "empty_reply"
    if len(cleaned) < 10 or len(cleaned) > 4000:
        return None, "suspicious_reply_length"
    return cleaned, "ai_phonetic_repair"
