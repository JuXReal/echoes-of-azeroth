# Echoes of Azeroth

Automatisierte **deutsche (deDE) KI-Sprachausgabe** für das WoW-Addon
[Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc).

Die Pipeline übernimmt den kompletten Weg vom englischen Original-Voicepack bis zum
spielfertigen deutschen Addon: Quest-Texte extrahieren, Stimmen mit **Coqui XTTS-v2**
klonen, jede Zeile mit **Faster-Whisper** automatisch validieren, per
**EBU R128 (−16 LUFS)** mastern und als `ChattyLittleNpc_<Expansion>_deDE_voiceovers`
installieren. Ein Web-Studio mit Live-Monitoring, A/B-Hörvergleich und optionaler
KI-Reparatur (OpenAI, OpenRouter, Google Gemini, DeepSeek oder Ollama) rundet den
Workflow ab.

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![TTS: Coqui XTTS-v2](https://img.shields.io/badge/TTS-Coqui_XTTS--v2-purple.svg)](https://github.com/coqui-ai/TTS)
[![QA: Faster-Whisper](https://img.shields.io/badge/QA-Faster--Whisper-emerald.svg)](https://github.com/SYSTRAN/faster-whisper)

---

## Features

- **Komplette Pipeline (7 Schritte):** Addon-Analyse, Voice-Seed-Extraktion,
  Skript- & Phonetik-Regie, Stimmensynthese, Whisper-QA-Schleife, Audio-Mastering
  mit rassenspezifischen FX und unabhängiger Quality-Audit.
- **Stimmenklonen:** 6–10 s lange 24-kHz-Seeds aus den englischen Originaldateien
  reproduzieren Stimmfarbe und Emotion der NPCs (z. B. Lor'themar, Umbric, Arator).
- **Automatische Qualitätssicherung:** CER/WER-Gate mit Retry-Schleife
  (Temperatur-/Penalty-Anpassung). Nach konfigurierbaren Fehlversuchen übernimmt
  optional eine externe KI die phonetische Reparatur des Skripts.
- **Web-Studio** (`http://127.0.0.1:8765`):
  - Live-Status je Quest (Schritt, Versuch, CER), Fortschritt und ETA
  - Statistik der Probleme in Anzahl und Prozent, aktualisiert in Echtzeit
  - A/B-Hörvergleich EN/DE, Einzel-Regenerierung fehlgeschlagener Zeilen
  - KI-Einstellungen inkl. Verbindungstest — API-Keys bleiben lokal
- **Race-FX & Mastering:** rassenspezifische DSP-Ketten (Blutelf, Leerenelf,
  Untoter, Troll, Tauren, Gnom, Goblin …) plus EBU R128 Loudness-Normalisierung.
- **Nahtloser Fallback:** nicht lokalisierte Zeilen fallen im Spiel automatisch
  auf die englischen Originale zurück.

## Voraussetzungen

| Komponente | Anforderung |
| :--- | :--- |
| Betriebssystem | Linux (getestet unter CachyOS/Arch); CPU-Betrieb möglich |
| GPU | NVIDIA mit CUDA empfohlen (z. B. RTX 4070 SUPER); sonst CPU-Fallback |
| World of Warcraft | Retail-Installation inkl. englischem Voicepack (`ChattyLittleNpc_<Expansion>_voiceovers`) und `SavedVariables/ChattyLittleNpc.lua` |
| Systempakete | `ffmpeg` (installiert `install.sh` automatisch) |

Die englischen Originalpakete sind zwingend erforderlich: Sie liefern die
Klon-Seeds, die kanonischen Dateinamen (`VoiceoversList.lua`) und den In-Game-Fallback.

## Installation

```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

`install.sh` richtet das Python-3.11-venv ein, installiert alle Abhängigkeiten
(PyTorch CUDA, Coqui XTTS-v2, Faster-Whisper) und legt `.env` aus `.env.example` an.

**Konfiguration (`.env`, git-ignored):**

| Variable | Bedeutung |
| :--- | :--- |
| `WOW_ADDONS_DIR` | Pfad zu `World of Warcraft/_retail_/Interface/AddOns` |
| `WOW_SAVED_VARS` | Pfad zur `SavedVariables/ChattyLittleNpc.lua` |
| `WOW_PLAYER_NAME` / `_CLASS` / `_RACE` | Platzhalter für Spielerdaten-Ersetzung |
| `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL` | Optionale KI-Reparatur (s. u.) |

Nicht-sekretive Einstellungen (LUFS, QA-Schwellen, Race-FX, Whisper-Modell) liegen
in `config.yaml`.

## Nutzung

### Web-Studio (empfohlen)

```bash
./launch_desktop.sh          # startet Server + Browser
# oder:
./start.py                   # Menü → Option 1
```

Im Browser `http://127.0.0.1:8765`:

1. Expansion wählen (Midnight, The War Within, Dragonflight …)
2. Aktion starten: 20-Quest-Pilot, vollständige Expansion oder Audit
3. Live-Validierung, ETA und Problemstatistik im Studio verfolgen
4. Fehlgeschlagene Quests per Klick regenerieren oder per A/B-Vergleich anhören

### Terminal

```bash
./start.py                    # interaktives Menü
./run_full_pipeline.sh Midnight
./run_full_pipeline.sh ALL    # alle 6 Expansionen (Overnight)
```

## Pipeline-Schritte

| # | Skript | Funktion |
| :--- | :--- | :--- |
| 1 | `01_addon_analyzer.py` | Lua-Parser, MD5-Port, SavedVariables- & Wowhead-Scraping |
| 2 | `02_voice_extractor.py` | 24-kHz-Mono-Voice-Seeds (per NPC / Archetyp / Zeile) |
| 3 | `03_script_agent.py` | Dialekt-Normalisierung, Num2Words, Warcraft-Phonetik, Prosodie |
| 4 | `04_tts_generator.py` | XTTS-v2-Synthese mit Speaker-Latent-Caching |
| 5 | `05_qa_validator.py` | Whisper-Transkription, CER/WER-Gate, Retry + KI-Reparatur |
| 6 | `06_audio_fx.py` | Race-FX, EBU R128 (−16 LUFS), OGG-Export, Addon-Paket + WoW-Installation |
| 7 | `07_independent_audit_100.py` | Unabhängige Stichprobe: Akustik, Post-FX-CER/WER, Release-Gate |

Alle Schritte schreiben ihren Fortschritt in
`output/qa_reports/live_state.json` — die Quelle für Live-Status, ETA und
KI-Aktivitätslog im Web-Studio.

## KI-Reparatur (optional)

Schlägt eine Zeile nach `ai.trigger_after_failures` (Standard: 3) Versuchen fehl,
lässt die Pipeline das Skript von einer externen KI phonetisch neu schreiben und
synthetisiert es erneut. Unterstützt werden:

| Provider | Standard-Base-URL |
| :--- | :--- |
| `openai` | `https://api.openai.com/v1` |
| `openrouter` | `https://openrouter.ai/api/v1` |
| `google` | `https://generativelanguage.googleapis.com/v1beta` |
| `deepseek` | `https://api.deepseek.com/v1` |
| `ollama` | `http://127.0.0.1:11434` (lokal, ohne Key) |

Konfiguration über das Studio (Seitenleiste → *KI-Einstellungen*) oder direkt in
`.env`. **Sicherheit:** API-Keys liegen ausschließlich in der git-ignorierten
`.env` — sie werden niemals in `config.yaml`, Reports, Logs oder API-Antworten
geschrieben oder zurückgegeben.

## Qualitätsverantwortung & Community

KI-Sprachsynthese kann vereinzelt Aussprachefehler oder Halluzinationen
enthalten. Die automatische QA und der 100-Quest-Audit sind Filter, keine
Garantie — **die finale Abnahme im Web-Studio liegt beim Nutzer**.

Generierte Pakete bitte nicht eigenmächtig auf CurseForge/Wago veröffentlichen.
Credit gehört **Tuubby** und dem Chatty-Little-NPC-Team sowie den Sprechern der
englischen Originalpakete; Veröffentlichungen nur nach Absprache mit den
offiziellen Maintainern.

## Projektstruktur

```text
echoes-of-azeroth/
├── install.sh                       # Ein-Klick-Installer
├── start.py                         # Interaktives Terminal-Menü
├── launch_desktop.sh                # Desktop-Starter für das Web-Studio
├── run_full_pipeline.sh             # Batch-Runner (einzelne Expansion oder ALL)
├── config.yaml                      # Zentrale Konfiguration (nicht-sekretiv)
├── .env.example                     # Vorlage für lokale Pfade & KI-Keys
├── pipeline/
│   ├── 01_addon_analyzer.py         # Lua-Parser, MD5, SavedVariables & Wowhead
│   ├── 02_voice_extractor.py        # 24-kHz-Mono-Voice-Seeds
│   ├── 03_script_agent.py           # Text-/Dialekt-Normalisierung & Phonetik
│   ├── 04_tts_generator.py          # XTTS-v2-Batch-Synthese (CUDA FP16)
│   ├── 05_qa_validator.py           # Whisper-QA-Schleife + KI-Reparatur
│   ├── 06_audio_fx.py               # Race-FX, Loudnorm, OGG & Addon-Export
│   ├── 07_independent_audit_100.py  # Unabhängiger Quality-Audit
│   ├── ai_client.py                 # Provider-Gateway (OpenAI, Gemini, …)
│   ├── live_state.py                # Live-Status/ETA/AI-Log fürs Web-Studio
│   └── regenerate_single.sh         # Einzelne Zeile regenerieren (TTS→QA→FX)
├── web/
│   ├── index.html                   # Studio-UI (Live-Monitoring, A/B, Settings)
│   └── serve.py                     # Lokaler Server & Job-Runner (Port 8765)
└── output/
    └── qa_reports/                  # Audit-Reports & live_state.json
```

## Credits & Lizenz

- [Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc): Tuubby & Team
- Englische Original-Voicepacks: Community-Sprecher und Kuratoren
- Open Source: [Coqui XTTS-v2](https://github.com/coqui-ai/TTS),
  [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper),
  [FFmpeg](https://ffmpeg.org/)
- Lizenz: MIT
