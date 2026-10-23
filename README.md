# 🎙️ Echoes of Azeroth
### *Multi-Language AI Voice Cloning & Mastering Suite for "Chatty Little NPC"*
*(Tested & Validated with German / `deDE` — Cross-Lingual Architecture Ready for 17+ Languages)*

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![TTS: Coqui XTTS-v2](https://img.shields.io/badge/TTS-Coqui_XTTS--v2_FP16-purple.svg)](https://github.com/coqui-ai/TTS)
[![QA: Faster-Whisper + 100-Quest Audit](https://img.shields.io/badge/QA-Faster--Whisper_%2B_100_Quest_Audit-emerald.svg)](https://github.com/SYSTRAN/faster-whisper)
[![Languages: Multi-Language (Tested: deDE)](https://img.shields.io/badge/Languages-Multi--Language_(Tested:_deDE)-teal.svg)](#-multi-language-architecture-17-languages)

---

### 🌐 Language / Sprache
* [🇬🇧 English Documentation](#-english-documentation)
* [🇩🇪 Deutsche Dokumentation](#-deutsche-dokumentation)

---

<a name="-english-documentation"></a>
# 🇬🇧 English Documentation

## ⚠️ Important Community Notice & User Quality Responsibility

> [!CAUTION]
> ### 1. YOU (THE USER) ARE PERSONALLY RESPONSIBLE FOR AUDIO QUALITY!
> **This pipeline is an open-source development tool.** AI-based speech synthesis (XTTS-v2) can occasionally produce pronunciation inaccuracies, unwanted hallucinations, or unnatural pauses.
> * **The automated 100-Quest Audit runs mandatorily after EVERY run** to catch major acoustic flaws and transcription drifts.
> * **However, YOU as the user are strictly responsible for personally reviewing and listening to your generated voiceover files** using the integrated A/B Web Studio (`http://127.0.0.1:8765`) before using or distributing them.

> [!WARNING]
> ### 2. DO NOT BLINDLY UPLOAD PACKS TO CURSEFORGE OR WAGO!
> **Please respect the work of the Chatty Little NPC creators!**  
> Full credit belongs to **Tuubby** and the **Chatty Little NPC** addon team, as well as the community contributors who created and recorded the original English voice packs.
> * Never publish generated packs under the official *Chatty Little NPC* brand name on public addon platforms.
> * If you want to contribute localized voiceovers to the broader community, always coordinate directly with the official *Chatty Little NPC* maintainers via Discord/GitHub first.

---

## 💡 Why the English Voiceover Packs Are Mandatory

**Echoes of Azeroth** does **not** replace the English voice packs from *Chatty Little NPC*. Instead, the English packs (`ChattyLittleNpc_<Expansion>_voiceovers`) are technically and artistically indispensable:

1. **Cross-Lingual Voice Cloning Seeds (Timbre & Emotion):**  
   Lore characters (*Lor'themar Theron*, *Liadrin*, *Turalyon*, *Arator*) and race archetypes have unique voice acting in the English original. Step 2 extracts clean 6–10 second voice seeds (24 kHz Mono WAV) from these English files so that `Coqui XTTS-v2` can recreate the exact same voice timbre, pitch, and age in your target language.
2. **Canonical Mapping (`VoiceoversList.lua`):**  
   The English packs define canonical QuestID phases (`QuestID_Desc.ogg`, `QuestID_Prog.ogg`, `QuestID_Comp.ogg`) and gossip hashes (`NPCID_Gossip_<MD5>.ogg`).
3. **Seamless In-Game Fallback (`voiceoverLanguageFallback`):**  
   *Chatty Little NPC* automatically plays localized files when present and seamlessly falls back to the English original audio when a quest line or gossip dialogue has not been localized yet.

---

## ⚡ Reference Hardware & Benchmarks

Measured on the author's primary development workstation running **CachyOS Linux**:

| Component | Specification |
| :--- | :--- |
| **OS** | **CachyOS Linux** (Kernel `7.2.9-2-cachyos`, Arch-based) |
| **Processor (CPU)** | **AMD Ryzen 9 7950X** (16 Cores / 32 Threads) |
| **Graphics (GPU)** | **NVIDIA GeForce RTX 4070 SUPER** (12 GB VRAM, CUDA FP16) |
| **RAM** | **48 GB DDR5** (`46 GiB` usable) |

### ⏱️ Per-Quest Execution Time (Average speech duration: ~15–25s)

| Step | Hardware Unit | Per Audio File | 20-Quest Pilot | 1,000 Quests Est. |
| :--- | :--- | :--- | :--- | :--- |
| **1. Analysis & Scraping** | CPU + Network | ~0.12s | ~2.5s | ~2 min |
| **2. Voice Seed Extraction** | CPU (FFmpeg) | ~0.35s *(cached)* | ~7s | ~2 min *(cached)* |
| **3. Script & Phonetics** | CPU / Hybrid LLM | ~0.05s | ~1s | ~1 min |
| **4. AI Voice Synthesis** | **GPU (RTX 4070S)** | **~4.5 – 5.5s** | ~1 min 50s | ~1.4 hrs |
| **5. In-Loop Whisper QA** | CPU (int8) / GPU | ~1.2s *(w/ retries)* | ~28s | ~20 min |
| **6. DSP & Loudnorm (-16 LUFS)** | CPU (FFmpeg Vorbis)| ~0.45s | ~9s | ~7.5 min |
| **7. Mandatory 100-Quest Audit** | CPU (Whisper + SF) | ~0.20s *(sampled)* | ~4s | ~20s *(100 sample)* |
| **TOTAL (End-to-End)** | **Ryzen 9 + RTX 4070S** | **~6.5 – 7.5s / quest** | **3m 24s** | **~1h 50m** |

---

## 🚀 Quickstart in 2 Steps

### 1. Run the One-Click Installer
```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

*(Copies `.env.example` to `.env` if desired to customize your local WoW AddOns path or character placeholder).*

### 2. Launching the Pipeline

You have two simple ways to run the pipeline without memorizing commands:

* **Option A: Web Studio & One-Click Launchpad (`http://127.0.0.1:8765`)**  
  Start via `./launch_desktop.sh` or `./start.py` (Option `1`). Select your expansion (`Midnight`, `The War Within`, `Dragonflight`, etc.) and click **`▶ START SELECTED ACTION`**.
* **Option B: Interactive Terminal Menu (`./start.py`)**  
  Run `./start.py` to pick from the interactive menu:
  * `[1]` Open Web Studio & Launchpad
  * `[2]` Run 20-Quest Pilot Test
  * `[3]` Run Full Expansion Localization
  * `[4]` Run Independent 100-Quest Quality Audit

---

## 🛡️ Mandatory Automatic 100-Quest Audit (`07_independent_audit_100.py`)

At the conclusion of **EVERY** pipeline run, the **Independent Quality Audit** is executed automatically:
1. **Random Sampling:** Automatically selects a randomized sample of up to 100 quests from the generated OGG files.
2. **Post-FX Verification:** Analyzes mastered OGG containers for clipping, dead air, duration, and re-transcribes them via `Faster-Whisper` to compute post-mastering CER / WER.
3. **User Responsibility Display:** Prints the audit scorecard and explicitly reminds you that you are responsible for testing the audio in-game and via the A/B Studio.

---

<br />
<hr />
<br />

<a name="-deutsche-dokumentation"></a>
# 🇩🇪 Deutsche Dokumentation

## ⚠️ Wichtiger Community-Hinweis & Qualitätsverantwortung

> [!CAUTION]
> ### 1. DU ALS NUTZER BIST PERSÖNLICH FÜR DIE QUALITÄT VERANTWORTLICH!
> **Diese Pipeline ist ein Open-Source Entwicklungs-Werkzeug.** KI-Sprachsynthese (XTTS-v2) kann vereinzelt Aussprachefehler, unpassende Betonungen oder Halluzinationen erzeugen.
> * **Der 100-Quest Qualitätscheck läuft zwingend automatisch nach JEDEM Durchlauf**, um technische Fehler und Ausreißer aufzuspüren.
> * **Dennoch bist DU als Nutzer dafür verantwortlich, die Audios im integrierten A/B-Webstudio (`http://127.0.0.1:8765`) persönlich anzuhören und gegenzuprüfen**, bevor du die Sprachpakete im Spiel nutzt oder weitergibst!

> [!WARNING]
> ### 2. BITTE NICHT BLIND NACH CURSEFORGE ODER WAGO HOCHLADEN!
> **Respektiere die monatelange Arbeit der Chatty Little NPC Entwickler und Community!**  
> Ein riesiges Dankeschön gebührt **Tuubby** und dem **Chatty Little NPC**-Team sowie allen Sprechern der englischen Originalpakete.
> * Lade niemals eigenmächtig generierte Pakete unter dem offiziellen Addon-Namen auf CurseForge hoch.
> * Wenn du lokalisierte Pakete offiziell der WoW-Community bereitstellen möchtest, stimme dich vorher im Discord/GitHub mit den Chatty Little NPC Autoren ab.

---

## 💡 Warum werden die englischen Originaldateien zwingend gebraucht?

**Echoes of Azeroth** ersetzt die englischen Sprachpakete nicht, sondern baut direkt auf ihnen auf:

1. **Cross-Lingual Voice Seeds (Stimmfarbe & Emotion):**  
   Lore-Charaktere (*Lor'themar*, *Liadrin*, *Turalyon*, *Arator*) und Rassen haben unverwechselbare Stimmen. Schritt 2 schneidet 6–10 Sekunden lange 24kHz-WAV-Seeds aus den englischen Dateien, damit `Coqui XTTS-v2` exakt diese Stimmfarbe auf Deutsch nachbilden kann.
2. **Kanonische Zuordnung (`VoiceoversList.lua`):**  
   Das Addon nutzt feste Dateinamen (`QuestID_Desc.ogg`, `QuestID_Prog.ogg`, `QuestID_Comp.ogg` und `NPCID_Gossip_<MD5>.ogg`).
3. **Nahtloser In-Game Fallback (`voiceoverLanguageFallback`):**  
   Noch nicht lokalisierte Dialoge greifen im Spiel automatisch und absturzfrei auf das englische Originalpaket zurück.

---

## ⚡ Referenz-Hardware & Benchmarks (Zeit pro Quest)

Entwickelt und gemessen auf folgendem System unter **CachyOS Linux**:

| Hardware | Spezifikation |
| :--- | :--- |
| **Betriebssystem** | **CachyOS Linux** (Kernel `7.2.9-2-cachyos`, Arch-Basis) |
| **Prozessor (CPU)** | **AMD Ryzen 9 7950X** (16 Kerne / 32 Threads) |
| **Grafikkarte (GPU)** | **NVIDIA GeForce RTX 4070 SUPER** (12 GB VRAM, CUDA FP16) |
| **Arbeitsspeicher (RAM)** | **48 GB DDR5** (`46 GiB` nutzbar) |

### ⏱️ Laufzeiten pro Quest (Durchschnitt bei ~15–25 Sek. Audiodauer)

| Schritt | Ausführung | Zeit pro Quest | 20-Quest Pilot | 1.000 Quests Est. |
| :--- | :--- | :--- | :--- | :--- |
| **1. Analyse & Scraping** | CPU + Web | ~0,12s | ~2,5s | ~2 Min. |
| **2. Voice-Seed Extraktion** | CPU (FFmpeg) | ~0,35s *(gecacht)* | ~7s | ~2 Min. *(gecacht)* |
| **3. Skript & Phonetik** | CPU / Hybrid-LLM | ~0,05s | ~1s | ~1 Min. |
| **4. KI-Sprachsynthese** | **GPU (RTX 4070S)** | **~4,5 – 5,5s** | ~1 Min. 50s | ~1,4 Std. |
| **5. In-Loop Whisper QA** | CPU (int8) / GPU | ~1,2s *(inkl. Retries)* | ~28s | ~20 Min. |
| **6. DSP & Loudnorm (-16 LUFS)** | CPU (FFmpeg Vorbis)| ~0,45s | ~9s | ~7,5 Min. |
| **7. Zwingender 100-Quest Audit** | CPU (Whisper + SF) | ~0,20s *(Stichprobe)* | ~4s | ~20s *(100 Quests)* |
| **GESAMT (End-to-End)** | **Ryzen 9 + RTX 4070S** | **~6,5 – 7,5s / Quest** | **3 Min. 24s** | **~1 Std. 50 Min.** |

---

## 🚀 Schnellstart in 2 Schritten

### 1. Ein-Klick-Installer ausführen
```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

### 2. Pipeline bedienen

* **Web-Studio im Browser (`http://127.0.0.1:8765`):**  
  Starte per Desktop-Icon oder `./launch_desktop.sh`, wähle im Dropdown deine Erweiterung (`Midnight`, `The War Within`, etc.) und klicke auf **`▶ START SELECTED ACTION`**.
* **Terminal-Startmenü (`./start.py`):**  
  Bietet eine übersichtliche Ziffernauswahl für Pilot-Tests, Komplett-Generierung und Audits.

---

## 🛡️ Zwingend automatischer 100-Quest Qualitätscheck

Nach **JEDEM** Durchlauf der Pipeline startet automatisch Schritt 7 (`07_independent_audit_100.py`):
1. **Zufallsauswahl:** Wählt bei jedem Durchlauf eine frische Stichprobe von bis zu 100 Quests aus den fertigen OGG-Dateien.
2. **Abrechnung & Post-FX Transkription:** Prüft Übersteuerung (Clipping), Leerlauf (Dead Air), Dauer und transkribiert die fertigen OGG-Dateien mit `Faster-Whisper` gegen das Skript.
3. **Nutzer-Verantwortung:** Gibt den Prüfbericht aus und erinnert daran, dass die Endabnahme im Web-Studio beim Nutzer liegt.

---

## 🏗️ Repository-Struktur

```text
echoes-of-azeroth/
├── install.sh                       # 1-Klick System- & Python-.venv-Installer
├── start.py                         # Interaktives Terminal-Startmenü
├── launch_desktop.sh                # Desktop-Starter für Browser & Studio
├── run_full_pipeline.sh             # Vollautomatischer Batch-Runner
├── config.yaml                      # Zentrale Konfiguration (Pfade, LUFS, Rassen-FX, QA)
├── pipeline/
│   ├── 01_addon_analyzer.py         # Lua-Parser, Custom-MD5 & Wowhead-Scraper
│   ├── 02_voice_extractor.py        # Schneidet 24kHz Mono WAV Voice-Seeds (6-10s)
│   ├── 03_script_agent.py           # Zweistufiges LLM-Routing & Phonetik-Regisseur
│   ├── 04_tts_generator.py          # Lokale CUDA FP16 Batch-Synthese (XTTS-v2)
│   ├── 05_qa_validator.py           # In-Loop Whisper ASR + Levenshtein Re-Synthesis
│   ├── 06_audio_fx.py               # FFmpeg Rassen-DSP, EBU R128 (-16 LUFS) & Addon-Export
│   └── 07_independent_audit_100.py  # Zwingender 100-Quest End-to-End Qualitätscheck (Random)
├── web/
│   ├── index.html                   # A/B-Hörvergleich-Studio + One-Click Launchpad
│   └── serve.py                     # Lokaler Webserver & Background-Job-Runner (Port 8765)
└── output/
    └── qa_reports/                  # JSON-Prüfberichte der Audits
```

---

## 🤝 Credits & License

* **Chatty Little NPC**: Tuubby & Team ([CurseForge](https://www.curseforge.com/wow/addons/chatty-little-npc)).
* **English Voiceover Community**: Unverzichtbare Sprecher und Kuratoren der englischen Originalpakete.
* **Open Source AI**: [Coqui XTTS-v2](https://github.com/coqui-ai/TTS), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [FFmpeg](https://ffmpeg.org/).
* **License**: MIT
