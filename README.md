# Echoes of Azeroth

Automated **German (deDE) AI voiceover localization** for the World of Warcraft addon
[Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc) —
from quest-text extraction over voice cloning (**Coqui XTTS-v2**), automatic
validation (**Faster-Whisper**) and mastering (**EBU R128, −16 LUFS**) to a
ready-to-install `ChattyLittleNpc_<Expansion>_deDE_voiceovers` addon pack.
A local web studio provides live monitoring, A/B listening, single-entry
regeneration and optional AI repair (OpenAI, OpenRouter, Google Gemini,
DeepSeek, Ollama).

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![TTS: Coqui XTTS-v2](https://img.shields.io/badge/TTS-Coqui_XTTS--v2-purple.svg)](https://github.com/coqui-ai/TTS)
[![QA: Faster-Whisper](https://img.shields.io/badge/QA-Faster--Whisper-emerald.svg)](https://github.com/SYSTRAN/faster-whisper)

---

- [English documentation](#english-documentation)
- [Deutsche Dokumentation](#deutsche-dokumentation)

---

## English documentation

### Why the English voiceover packs are required

The original English packs (`ChattyLittleNpc_<Expansion>_voiceovers`) are not
replaced by this pipeline — they are technically required for three reasons:

1. **Voice-cloning seeds.** XTTS-v2 is a speaker-conditioned model: it needs a
   reference clip to compute the speaker conditioning (`gpt_cond_latent` +
   `speaker_embedding` via `get_conditioning_latents`). Step 2
   (`02_voice_extractor.py`) slices clean 6–10 s, 24 kHz mono WAV seeds from
   the English OGGs — one per lore NPC / race-gender archetype and one per
   dialogue line. Without these clips there is no voice identity to clone;
   the model would synthesize with an unrelated default voice.
2. **Canonical file mapping.** `VoiceoversList.lua` in the English pack
   defines the exact filenames the addon looks up
   (`<QuestID>_Desc|Prog|Comp.ogg`, `<NPCID>_Gossip_<MD5>[_<Gender>].ogg`)
   together with the OggVorbis durations. The pipeline ports the addon's Lua
   MD5 hash (`CLN.MD5:GenerateHash`) bit-exactly so gossip hashes match, and
   the generated deDE pack mirrors the English filenames 1:1 — otherwise the
   addon would never find the localized files.
3. **In-game fallback.** Chatty Little NPC iterates its voice packs with a
   per-file fallback to the English originals (`voiceoverLanguageFallback`).
   The English pack therefore guarantees complete in-game coverage for every
   line that has not been localized yet.

The German source texts come from `SavedVariables/ChattyLittleNpc.lua`
(texts the addon already recorded in-game) and — for quests not yet recorded —
from a cached `de.wowhead.com` scraper.

### Requirements

| Component | Requirement |
| :--- | :--- |
| OS | Linux (tested on CachyOS/Arch); CPU operation possible |
| GPU | NVIDIA + CUDA recommended (e.g. RTX 4070 SUPER); CPU fallback otherwise |
| World of Warcraft | Retail installation with the English pack `ChattyLittleNpc_<Expansion>_voiceovers` installed and `SavedVariables/ChattyLittleNpc.lua` present |
| System packages | `ffmpeg` (installed automatically by `install.sh`) |

### Installation

```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

`install.sh` creates the Python 3.11 venv, installs all dependencies
(PyTorch CUDA, Coqui XTTS-v2, Faster-Whisper, `nvidia-cublas-cu12` for the
Whisper CUDA runtime) and copies `.env.example` to `.env`.

### Configuration — WoW paths (.env)

All local paths live in the git-ignored `.env` and override the placeholders
in `config.yaml`:

| Variable | Meaning |
| :--- | :--- |
| `WOW_ADDONS_DIR` | Path to `World of Warcraft/_retail_/Interface/AddOns` |
| `WOW_SAVED_VARS` | Path to `WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua` |
| `WOW_PLAYER_NAME` / `_CLASS` / `_RACE` | Placeholders used to strip player data from texts |

Examples:

```bash
# Linux — native install (Lutris/Wine)
WOW_ADDONS_DIR="$HOME/Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns"
WOW_SAVED_VARS="$HOME/Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua"

# Linux — Steam/Proton (compatdata): find the correct <proton-prefix-id> in
# ~/.local/share/Steam/steamapps/compatdata/ (usually the one matching the
# WoW app id)
WOW_ADDONS_DIR="/home/<user>/.local/share/Steam/steamapps/compatdata/<proton-prefix-id>/pfx/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns"
WOW_SAVED_VARS="/home/<user>/.local/share/Steam/steamapps/compatdata/<proton-prefix-id>/pfx/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua"

# Windows
WOW_ADDONS_DIR="C:\\Program Files (x86)\\World of Warcraft\\_retail_\\Interface\\AddOns"
WOW_SAVED_VARS="C:\\Program Files (x86)\\World of Warcraft\\_retail_\\WTF\\Account\\<ACCOUNT>\\SavedVariables\\ChattyLittleNpc.lua"
```

Diagnostics: if the English audio players in the web studio return 404,
`WOW_ADDONS_DIR` is wrong or the English voiceover pack is not installed.

Non-secret settings (LUFS target, QA thresholds, race FX chains, Whisper
model) live in `config.yaml`.

### Usage

**Web studio (recommended):**

```bash
./launch_desktop.sh        # starts the server and opens the browser
# or: ./start.py -> option 1
```

Open `http://127.0.0.1:8765`: pick an expansion, start the 20-quest pilot,
the full expansion or an audit, watch live progress/ETA/problem statistics
and regenerate or A/B-listen to failed entries.

**CLI:**

```bash
./start.py                              # interactive menu
./run_full_pipeline.sh Midnight         # one expansion
./run_full_pipeline.sh ALL              # all 6 expansions (overnight)
./restart_server.sh                     # stop all jobs + restart the studio
```

### Pipeline steps

| # | Script | Function |
| :--- | :--- | :--- |
| 1 | `01_addon_analyzer.py` | Lua parsing, MD5 port, SavedVariables + Wowhead DE scraping |
| 2 | `02_voice_extractor.py` | 24 kHz mono voice seeds (per NPC / archetype / line) |
| 3 | `03_script_agent.py` | Number/dialect normalization, Warcraft phonetics, prosody |
| 4 | `04_tts_generator.py` | XTTS-v2 synthesis with speaker-latent caching |
| 5 | `05_qa_validator.py` | Whisper transcription, CER/WER gate, retries + AI repair |
| 6 | `06_audio_fx.py` | Race FX, EBU R128 (−16 LUFS), OGG export, addon install |
| 7 | `07_independent_audit_100.py` | Independent sample audit: acoustics, post-FX CER/WER |

All steps write progress (current quest, attempt, CER, counts, ETA, AI call
log) to `output/qa_reports/live_state.json`, the source of the web studio's
live view.

### AI repair (optional)

After `ai.trigger_after_failures` (default 3) failed attempts, the pipeline
asks the configured AI to rewrite the phonetic script, then re-synthesizes
and re-validates:

| Provider | Default base URL |
| :--- | :--- |
| `openai` | `https://api.openai.com/v1` |
| `openrouter` | `https://openrouter.ai/api/v1` |
| `google` | `https://generativelanguage.googleapis.com/v1beta` |
| `deepseek` | `https://api.deepseek.com/v1` |
| `ollama` | `http://127.0.0.1:11434` (local, no key) |

Configure via the studio sidebar (*KI-Einstellungen* — includes a "load
models" catalog and a connection test) or directly in `.env`
(`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`).
**Security:** API keys live exclusively in the git-ignored `.env`; they are
never written to `config.yaml`, reports, logs or API responses. Token usage
and estimated cost per call are tracked in `output/qa_reports/ai_usage.json`
and displayed in the studio.

> Note: reasoning models (e.g. `deepseek-reasoner`) can return empty content
> because they spend the output budget on reasoning — use a chat model such
> as `deepseek-chat`.

### Quality responsibility & community

AI speech synthesis can occasionally mispronounce or hallucinate. The QA loop
and the 100-quest audit are filters, not guarantees — **final acceptance by
listening in the web studio is the user's responsibility.** Please do not
upload generated packs to CurseForge/Wago without coordination: credit
belongs to Tuubby, the Chatty Little NPC team and the community behind the
original English voice packs.

### Repository structure

```text
echoes-of-azeroth/
├── install.sh                       # one-click installer
├── start.py                         # interactive CLI menu
├── launch_desktop.sh                # desktop launcher (starts studio + browser)
├── restart_server.sh                # stops jobs on port 8765 + restarts the studio
├── run_full_pipeline.sh             # batch runner (one expansion or ALL)
├── config.yaml                      # non-secret configuration
├── .env.example                     # template for local paths & AI keys
├── pipeline/
│   ├── 01_addon_analyzer.py         # Lua parser, MD5, SavedVariables & Wowhead
│   ├── 02_voice_extractor.py        # 24 kHz mono voice seeds
│   ├── 03_script_agent.py           # normalization & Warcraft phonetics
│   ├── 04_tts_generator.py          # XTTS-v2 batch synthesis (CUDA FP16)
│   ├── 05_qa_validator.py           # Whisper QA loop + AI repair
│   ├── 06_audio_fx.py               # race FX, loudnorm, OGG & addon export
│   ├── 07_independent_audit_100.py  # independent quality audit
│   ├── ai_client.py                 # provider gateway (OpenAI, Gemini, …)
│   ├── cuda_env.py                  # CUDA runtime setup for Faster-Whisper
│   ├── live_state.py                # live status/ETA/AI log for the studio
│   └── regenerate_single.sh         # regenerate one entry (TTS → QA → FX)
├── web/
│   ├── index.html                   # studio UI (live monitoring, A/B, settings)
│   └── serve.py                     # local server & job runner (port 8765)
└── output/
    └── qa_reports/                  # audit reports, live_state.json, ai_usage.json
```

### Credits & License

- [Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc): Tuubby & team
- Original English voice packs: community voice actors and curators
- Open source: [Coqui XTTS-v2](https://github.com/coqui-ai/TTS), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [FFmpeg](https://ffmpeg.org/)
- License: MIT

---

## Deutsche Dokumentation

### Warum die englischen Sounddateien zwingend nötig sind

Die englischen Originalpakete (`ChattyLittleNpc_<Expansion>_voiceovers`)
werden nicht ersetzt — sie sind aus drei technischen Gründen erforderlich:

1. **Voice-Cloning-Seeds.** XTTS-v2 ist sprecherkonditioniert: Das Modell
   braucht einen Referenzclip, um die Sprecherkonditionierung zu berechnen
   (`gpt_cond_latent` + `speaker_embedding` via `get_conditioning_latents`).
   Schritt 2 (`02_voice_extractor.py`) schneidet saubere 6–10 s lange,
   24-kHz-Mono-WAV-Seeds aus den englischen OGGs — pro Lore-NPC /
   Rasse-Geschlecht-Archetyp und pro Dialogzeile. Ohne diese Clips gibt es
   keine Stimmidentität, die geklont werden kann; das Modell würde mit einer
   fremden Standardstimme sprechen.
2. **Kanonische Dateizuordnung.** `VoiceoversList.lua` im englischen Paket
   definiert die exakten Dateinamen, nach denen das Addon sucht
   (`<QuestID>_Desc|Prog|Comp.ogg`, `<NPCID>_Gossip_<MD5>[_<Gender>].ogg`),
   samt OggVorbis-Dauern. Die Pipeline portiert den Lua-MD5 des Addons
   (`CLN.MD5:GenerateHash`) bitgenau, damit die Gossip-Hashes stimmen; das
   generierte deDE-Paket spiegelt die englischen Dateinamen 1:1 — sonst
   würde das Addon die lokalisierten Dateien nie finden.
3. **In-Game-Fallback.** Chatty Little NPC iteriert seine Sprachpakete mit
   Fallback pro Datei auf die englischen Originale
   (`voiceoverLanguageFallback`). Das englische Paket garantiert damit eine
   lückenlose Abdeckung für alle noch nicht lokalisierten Zeilen.

Die deutschen Quelltexte stammen aus `SavedVariables/ChattyLittleNpc.lua`
(im Spiel bereits aufgezeichnete Texte) und — für noch nicht aufgezeichnete
Quests — aus einem gecachten `de.wowhead.com`-Scraper.

### Voraussetzungen

| Komponente | Anforderung |
| :--- | :--- |
| Betriebssystem | Linux (getestet unter CachyOS/Arch); CPU-Betrieb möglich |
| GPU | NVIDIA + CUDA empfohlen (z. B. RTX 4070 SUPER); sonst CPU-Fallback |
| World of Warcraft | Retail-Installation mit installiertem englischen Paket `ChattyLittleNpc_<Expansion>_voiceovers` und vorhandener `SavedVariables/ChattyLittleNpc.lua` |
| Systempakete | `ffmpeg` (wird von `install.sh` automatisch installiert) |

### Installation

```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

`install.sh` richtet das Python-3.11-venv ein, installiert alle
Abhängigkeiten (PyTorch CUDA, Coqui XTTS-v2, Faster-Whisper,
`nvidia-cublas-cu12` für die Whisper-CUDA-Laufzeit) und kopiert
`.env.example` nach `.env`.

### Konfiguration — WoW-Pfade (.env)

Alle lokalen Pfade stehen in der git-ignorierten `.env` und überschreiben die
Platzhalter in `config.yaml`:

| Variable | Bedeutung |
| :--- | :--- |
| `WOW_ADDONS_DIR` | Pfad zu `World of Warcraft/_retail_/Interface/AddOns` |
| `WOW_SAVED_VARS` | Pfad zu `WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua` |
| `WOW_PLAYER_NAME` / `_CLASS` / `_RACE` | Platzhalter zum Entfernen von Spielerdaten aus den Texten |

Beispiele:

```bash
# Linux — native Installation (Lutris/Wine)
WOW_ADDONS_DIR="$HOME/Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns"
WOW_SAVED_VARS="$HOME/Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua"

# Linux — Steam/Proton (compatdata): die passende <proton-prefix-id> findest du
# unter ~/.local/share/Steam/steamapps/compatdata/ (meist die der WoW-App-ID)
WOW_ADDONS_DIR="/home/<user>/.local/share/Steam/steamapps/compatdata/<proton-prefix-id>/pfx/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns"
WOW_SAVED_VARS="/home/<user>/.local/share/Steam/steamapps/compatdata/<proton-prefix-id>/pfx/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ChattyLittleNpc.lua"

# Windows
WOW_ADDONS_DIR="C:\\Program Files (x86)\\World of Warcraft\\_retail_\\Interface\\AddOns"
WOW_SAVED_VARS="C:\\Program Files (x86)\\World of Warcraft\\_retail_\\WTF\\Account\\<ACCOUNT>\\SavedVariables\\ChattyLittleNpc.lua"
```

Diagnose: Liefern die englischen Audio-Player im Web-Studio einen 404, ist
`WOW_ADDONS_DIR` falsch oder das englische Sprachpaket nicht installiert.

Nicht-sekretive Einstellungen (LUFS-Ziel, QA-Schwellen, Race-FX-Ketten,
Whisper-Modell) stehen in `config.yaml`.

### Nutzung

**Web-Studio (empfohlen):**

```bash
./launch_desktop.sh        # startet Server + Browser
# oder: ./start.py -> Option 1
```

`http://127.0.0.1:8765` öffnen: Expansion wählen, 20-Quest-Pilot,
vollständige Expansion oder Audit starten, Live-Fortschritt/ETA/
Problemstatistik verfolgen und fehlgeschlagene Einträge regenerieren oder
per A/B anhören.

**CLI:**

```bash
./start.py                              # interaktives Menü
./run_full_pipeline.sh Midnight         # eine Expansion
./run_full_pipeline.sh ALL              # alle 6 Expansionen (Overnight)
./restart_server.sh                     # alle Jobs stoppen + Studio neu starten
```

### Pipeline-Schritte

| # | Skript | Funktion |
| :--- | :--- | :--- |
| 1 | `01_addon_analyzer.py` | Lua-Parser, MD5-Port, SavedVariables + Wowhead-DE-Scraping |
| 2 | `02_voice_extractor.py` | 24-kHz-Mono-Voice-Seeds (pro NPC / Archetyp / Zeile) |
| 3 | `03_script_agent.py` | Zahlen-/Dialekt-Normalisierung, Warcraft-Phonetik, Prosodie |
| 4 | `04_tts_generator.py` | XTTS-v2-Synthese mit Speaker-Latent-Caching |
| 5 | `05_qa_validator.py` | Whisper-Transkription, CER/WER-Gate, Retries + KI-Reparatur |
| 6 | `06_audio_fx.py` | Race-FX, EBU R128 (−16 LUFS), OGG-Export, Addon-Installation |
| 7 | `07_independent_audit_100.py` | Unabhängige Stichprobe: Akustik, Post-FX-CER/WER |

Alle Schritte schreiben ihren Fortschritt (aktuelle Quest, Versuch, CER,
Zähler, ETA, KI-Aufruf-Log) in `output/qa_reports/live_state.json` — die
Quelle der Live-Ansicht im Web-Studio.

### KI-Reparatur (optional)

Nach `ai.trigger_after_failures` (Standard: 3) Fehlversuchen lässt die
Pipeline das Skript von der konfigurierten KI phonetisch neu schreiben,
synthetisiert erneut und prüft noch einmal:

| Provider | Standard-Base-URL |
| :--- | :--- |
| `openai` | `https://api.openai.com/v1` |
| `openrouter` | `https://openrouter.ai/api/v1` |
| `google` | `https://generativelanguage.googleapis.com/v1beta` |
| `deepseek` | `https://api.deepseek.com/v1` |
| `ollama` | `http://127.0.0.1:11434` (lokal, ohne Key) |

Konfiguration über die Studio-Seitenleiste (*KI-Einstellungen* — mit
„Modelle laden"-Katalog und Verbindungstest) oder direkt in `.env`
(`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`).
**Sicherheit:** API-Keys liegen ausschließlich in der git-ignorierten
`.env`; sie werden nie in `config.yaml`, Reports, Logs oder API-Antworten
geschrieben. Token-Verbrauch und geschätzte Kosten pro Aufruf werden in
`output/qa_reports/ai_usage.json` geführt und im Studio angezeigt.

> Hinweis: Reasoning-Modelle (z. B. `deepseek-reasoner`) liefern teils leere
> Antworten, weil das Output-Budget für Gedankengänge verbraucht wird — ein
> Chat-Modell wie `deepseek-chat` verwenden.

### Qualitätsverantwortung & Community

KI-Sprachsynthese kann vereinzelt Aussprachefehler oder Halluzinationen
enthalten. QA-Schleife und 100-Quest-Audit sind Filter, keine Garantie —
**die finale Abnahme per Anhören im Web-Studio liegt beim Nutzer.**
Generierte Pakete bitte nicht ohne Absprache auf CurseForge/Wago
veröffentlichen: Der Dank gilt Tuubby, dem Chatty-Little-NPC-Team und der
Community hinter den englischen Original-Sprachpaketen.

### Projektstruktur

```text
echoes-of-azeroth/
├── install.sh                       # Ein-Klick-Installer
├── start.py                         # Interaktives CLI-Menü
├── launch_desktop.sh                # Desktop-Starter (Studio + Browser)
├── restart_server.sh                # Jobs auf Port 8765 stoppen + Studio neu starten
├── run_full_pipeline.sh             # Batch-Runner (eine Expansion oder ALL)
├── config.yaml                      # Nicht-sekretive Konfiguration
├── .env.example                     # Vorlage für lokale Pfade & KI-Keys
├── pipeline/
│   ├── 01_addon_analyzer.py         # Lua-Parser, MD5, SavedVariables & Wowhead
│   ├── 02_voice_extractor.py        # 24-kHz-Mono-Voice-Seeds
│   ├── 03_script_agent.py           # Normalisierung & Warcraft-Phonetik
│   ├── 04_tts_generator.py          # XTTS-v2-Batch-Synthese (CUDA FP16)
│   ├── 05_qa_validator.py           # Whisper-QA-Schleife + KI-Reparatur
│   ├── 06_audio_fx.py               # Race-FX, Loudnorm, OGG & Addon-Export
│   ├── 07_independent_audit_100.py  # Unabhängiger Quality-Audit
│   ├── ai_client.py                 # Provider-Gateway (OpenAI, Gemini, …)
│   ├── cuda_env.py                  # CUDA-Laufzeit-Setup für Faster-Whisper
│   ├── live_state.py                # Live-Status/ETA/AI-Log fürs Studio
│   └── regenerate_single.sh         # Eine Zeile regenerieren (TTS → QA → FX)
├── web/
│   ├── index.html                   # Studio-UI (Live-Monitoring, A/B, Settings)
│   └── serve.py                     # Lokaler Server & Job-Runner (Port 8765)
└── output/
    └── qa_reports/                  # Audit-Reports, live_state.json, ai_usage.json
```

### Credits & Lizenz

- [Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc): Tuubby & Team
- Englische Original-Sprachpakete: Community-Sprecher und Kuratoren
- Open Source: [Coqui XTTS-v2](https://github.com/coqui-ai/TTS), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [FFmpeg](https://ffmpeg.org/)
- Lizenz: MIT
