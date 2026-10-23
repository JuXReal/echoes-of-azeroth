# 🎙️ Echoes of Azeroth
### *Multi-Language AI Voice Cloning & Mastering Suite for "Chatty Little NPC"*
*(Tested & Validated with German / `deDE` — Architecture Ready for 17+ Languages)*

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![TTS: Coqui XTTS-v2](https://img.shields.io/badge/TTS-Coqui_XTTS--v2_FP16-purple.svg)](https://github.com/coqui-ai/TTS)
[![QA: Faster-Whisper + 100-Quest Audit](https://img.shields.io/badge/QA-Faster--Whisper_%2B_100_Quest_Audit-emerald.svg)](https://github.com/SYSTRAN/faster-whisper)
[![Languages: Multi-Language (Tested: deDE)](https://img.shields.io/badge/Languages-Multi--Language_(Tested:_deDE)-teal.svg)](#🌐-multi-language-architektur-17-sprachen)

> [!CAUTION]
> ### 🇬🇧 IMPORTANT COMMUNITY NOTICE (PLEASE READ BEFORE SHARING!)
> **Please DO NOT blindly upload generated voiceover packs to CurseForge or Wago!**  
> Please respect the hard work of the **Chatty Little NPC** addon creators (**Tuubby** and contributors) and the dedicated community contributors who created, recorded, and curated the original English voiceover files.
>
> * **Always run the Independent 100-Quest Quality Audit (`pipeline/07_independent_audit_100.py`)** and listen to the samples in the A/B Web Studio before sharing any generated files.
> * **Never upload unauthorized or unverified packs under the official *Chatty Little NPC* name on CurseForge.** If you wish to contribute localized packs officially, always coordinate directly with the original *Chatty Little NPC* addon authors first and give full credit to both the addon team and the English voiceover community.

---

## 🌍 Über das Projekt / Overview

**Echoes of Azeroth** ist eine vollautomatisierte, reproduzierbare Open-Source-Lokalisierungs-Pipeline für Linux & Windows (WSL2). Sie analysiert die englischen Original-Sprachpakete des beliebten World of Warcraft Addons **"Chatty Little NPC"**, extrahiert daraus saubere 24-kHz-Stimm-Referenzen (Cross-Lingual Zero-Shot Voice Cloning), übersetzt bzw. inszeniert die Zielsprachen-Texte dramaturgisch und generiert ein fertiges, nach **EBU R128 (-16 LUFS)** gemastertes Addon-Paket (`ChattyLittleNpc_<Expansion>_<Locale>_voiceovers`).

* **Vollständig getestet & validiert mit:** **Deutsch (`deDE`)**
* **Unterstützte Erweiterungen:**
  * `Midnight` (*World of Warcraft: Midnight*)
  * `The_War_Within` (*The War Within*)
  * `Dragonflight`
  * `Battle_for_Azeroth`
  * `Wrath_of_the_Lich_King`
  * `Vanilla` (*Classic*)

---

## 🌐 Multi-Language-Architektur (17+ Sprachen)

Obwohl die Pipeline primär für **Deutsch (`deDE`)** entwickelt und validiert wurde, ist die gesamte technische Kette **sprachunabhängig (Cross-Lingual)** aufgebaut:
* **Cross-Lingual Voice Cloning (`Coqui XTTS-v2`):** Klonen einer englischen Referenzstimme in **17 Sprachen** (`de`, `fr`, `es`, `it`, `pt`, `pl`, `ru`, `nl`, `tr`, `cs`, `hu`, `ko`, `zh-cn`, `ja`, `ar`, `hi`) unter Beibehaltung der englischen Original-Stimmfarbe.
* **Multilinguale QA (`Faster-Whisper`):** Unterstützt automatische Spracherkennung und Wort-/Zeichenfehlerraten-Prüfung (WER/CER) für über 90 Sprachen.
* **Lokalisierte Quest-Datenquellen (`Wowhead` & `SavedVariables`):** Über Subdomains (`de.wowhead.com`, `fr.wowhead.com`, `es.wowhead.com`, `it.wowhead.com`, `pt.wowhead.com`, `ru.wowhead.com`, `ko.wowhead.com`, `cn.wowhead.com`) sowie den In-Game-Mitschnitt von *Chatty Little NPC* lassen sich beliebige WoW-Client-Sprachen (`deDE`, `frFR`, `esES`, `esMX`, `itIT`, `ptBR`, `ruRU`, `koKR`, `zhCN`) anbinden.

---

## 🇬🇧 / 🇩🇪 Warum werden die englischen Original-Sprachdateien zwingend benötigt?
*(Why You MUST Install the Original English Voiceover Packs)*

**Echoes of Azeroth** ist **kein Ersatz** für die englischen Original-Pakete von *Chatty Little NPC*, sondern baut technisch und künstlerisch direkt auf der Arbeit der englischen Community auf. Die englischen Pakete (`ChattyLittleNpc_<Expansion>_voiceovers`) müssen aus **drei zwingenden Gründen** installiert sein:

1. **Cross-Lingual Zero-Shot Voice Cloning (Stimmfarbe, Charakter & Emotion):**  
   In WoW haben hunderte Lore-Charaktere (z. B. *Lor'themar Theron*, *Liadrin*, *Turalyon*, *Arator*) sowie Rassen-Archetypen (Blutelfen, Leerenelfen, Amani-Trolle, Untote, Tauren) eine unverwechselbare englische Originalstimme. Schritt 2 unserer Pipeline (`02_voice_extractor.py`) schneidet aus den englischen Original-OGGs die akustisch saubersten 6–10 Sekunden langen Sprach-Seeds (24 kHz Mono WAV) heraus. Nur durch diese englischen Vorlagen kann `Coqui XTTS-v2` exakt dieselbe Stimmfarbe, das Alter und das Timbre des jeweiligen NPCs in deiner Zielsprache reproduzieren!
2. **Kanonisches Quest-, Phasen- & NPC-Mapping (`VoiceoversList.lua`):**  
   Die englischen Originalpakete definieren die exakte Dateistruktur (`QuestID_Desc.ogg`, `QuestID_Prog.ogg`, `QuestID_Comp.ogg` sowie `NPCID_Gossip_<MD5>.ogg`). Unser Analyzer (`01_addon_analyzer.py`) liest die englische `VoiceoversList.lua` aus, um genau zu wissen, für welche Quest-IDs und Dialogphasen im Spiel überhaupt Sprachausgabe existiert.
3. **Nahtloser In-Game Fallback (`voiceoverLanguageFallback`):**  
   Das Haupt-Addon *Chatty Little NPC* iteriert im Spiel über alle geladenen Sprachpakete (`CLN:IterateVoiceoverPacks()`). Wenn du zum Testen erst einen Teil einer Erweiterung (z. B. den 20-Quest-Piloten) generiert hast, spielt das Addon für alle lokalisierten Treffer deine neuen Sprachdateien ab und greift für noch nicht übersetzte Quests oder Gossip-Zeilen automatisch und absturzfrei auf das englische Originalpaket zurück!

---

## ⚡ Referenz-Hardware & Benchmark (Zeit pro Quest)

Die Pipeline wurde auf folgendem Referenz-System unter Linux entwickelt, gemessen und validiert:

| Komponente | Referenz-Spezifikation |
| :--- | :--- |
| **Betriebssystem** | **CachyOS Linux** (Kernel `7.2.9-2-cachyos`, Arch-basiert) |
| **Prozessor (CPU)** | **AMD Ryzen 9 7950X** (16 Kerne / 32 Threads) |
| **Grafikkarte (GPU)** | **NVIDIA GeForce RTX 4070 SUPER** (12 GB VRAM, CUDA FP16) |
| **Arbeitsspeicher (RAM)** | **48 GB DDR5** (`46 GiB` nutzbar) |

### ⏱️ Gemessene Laufzeiten pro Quest (Durchschnitt bei ~15–25 Sek. Sprechdauer pro Quest)

| Pipeline-Schritt | Hardware-Einheit | Zeit pro Quest-Audio | Zeit für 20 Quests (Pilot) | Hochrechnung 1.000 Quests |
| :--- | :--- | :--- | :--- | :--- |
| **1. Addon-Analyse & Wowhead-Scraping** | CPU (8 Threads) + Netzwerk | **~0,12 s** | ~2,5 Sek. | ~2 Min. |
| **2. Voice-Seed-Extraktion (24 kHz WAV)** | CPU (`ffmpeg` Denoise/Trim) | **~0,35 s** *(einmalig pro NPC)* | ~7 Sek. | ~2 Min. *(gecacht)* |
| **3. Skript-Aufbereitung & Phonetik** | CPU / Hybrid-LLM | **~0,05 s** | ~1 Sek. | ~1 Min. |
| **4. KI-Sprachsynthese (`XTTS-v2` FP16)** | **GPU** (RTX 4070 SUPER) | **~4,5 – 5,5 s** | ~1 Min. 50 Sek. | ~1,4 Std. |
| **5. In-Loop QA (`Faster-Whisper` + Retry)** | CPU (`int8`, 8 Threads) / GPU | **~1,2 s** *(inkl. 15% Retry-Quote)* | ~28 Sek. | ~20 Min. |
| **6. Audio-Mastering (`EBU R128` + Rassen-FX)** | CPU (`ffmpeg` 2-Pass + Vorbis) | **~0,45 s** | ~9 Sek. | ~7,5 Min. |
| **7. Unabhängiger 100-Quest Qualitäts-Test** | CPU (`Faster-Whisper` + `soundfile`) | **~0,20 s** *(Stichprobe 100)* | ~4 Sek. | ~20 Sek. *(für 100 Quests)* |
| **GESAMT (End-to-End inkl. QA & Mastering)** | **Ryzen 9 7950X + RTX 4070S** | **ca. 6,5 – 7,5 Sekunden / Quest** | **3 Min. 24 Sek.** | **ca. 1 Std. 50 Min.** |

> [!TIP]
> **Automatische Fortsetzung (Checkpoint-Resume):**  
> Du musst eine komplette Erweiterung (z. B. *Midnight* mit ~2.411 Quest-Phasen ≈ **ca. 4 bis 4,5 Stunden** Gesamtlaufzeit auf einer RTX 4070 SUPER) **nicht am Stück** durchlaufen lassen! Alle Skripte überspringen bereits erfolgreich geprüfte Dateien automatisch. Du kannst jederzeit pausieren, WoW spielen und später nahtlos weitermachen.

---

## 🚀 Schnellstart in 2 Schritten (Quickstart)

### 1. Ein-Klick-Installer ausführen (`./install.sh`)
Das mitgelieferte Installer-Skript prüft und installiert automatisch alle Systemabhängigkeiten (`ffmpeg`, `sox`, `python3.11` auf Arch/CachyOS, Ubuntu/Debian oder Fedora), erstellt das isolierte `.venv` und installiert PyTorch (CUDA), Coqui XTTS-v2 sowie Faster-Whisper:

```bash
git clone https://github.com/JuXReal/echoes-of-azeroth.git
cd echoes-of-azeroth
./install.sh
```

---

### 2. Start-Button im Browser oder Start-Menü nutzen (`./start.py`)

Du hast zwei komfortable Möglichkeiten, die Pipeline zu bedienen – ganz ohne komplizierte Kommandozeilen-Parameter:

#### Option A: Grafischer Start-Button im Browser (`http://127.0.0.1:8765`)
Starte das Studio über das Desktop-Icon oder `./start.py` (Option `5`) und öffne **http://127.0.0.1:8765**:
* Oben im **One-Click Launchpad** wählst du im Dropdown-Menü einfach die Erweiterung (`Midnight`, `The War Within`, `Dragonflight`, etc.) und den Modus aus und klickst auf **`▶ START SELECTED ACTION`**.
* Ein integriertes Live-Terminal zeigt dir den Fortschritt in Echtzeit, während du darunter im **A/B-Player** direkt das englische Original gegen die neue lokalisierte Sprachausgabe probehören kannst.

#### Option B: Interaktives Terminal-Startmenü (`./start.py`)
Starte einfach den Launcher und wähle per Zahlentaste deine gewünschte Erweiterung und Aktion:

```bash
./start.py
```

* **`[1] 20-Quest Pilot-Test`** (~3–4 Min. — ideal zum schnellen Ausprobieren)
* **`[2] Komplette Erweiterung generieren (Quests)`** (Full Expansion Batch mit Auto-Resume)
* **`[3] Komplette Erweiterung + Gossip generieren`** (Inklusive gesammelter `SavedVariables`)
* **`[4] Unabhängiger 100-Quest Qualitäts-Test`** (`07_independent_audit_100.py`)
* **`[5] A/B Web-Studio & Start-Button öffnen`** (`http://127.0.0.1:8765`)

---

## 🔬 Unabhängiger 100-Quest Qualitäts-Test (`07_independent_audit_100.py`)

Bevor ein generiertes Sprachpaket im Spiel genutzt oder mit Freunden geteilt wird, führt **Echoes of Azeroth** einen **unabhängigen Qualitäts-Test über bis zu 100 zufällig gezogene Quests** durch (automatisch am Ende von `./run_full_pipeline.sh` oder jederzeit einzeln startbar):

```bash
.venv/bin/python pipeline/07_independent_audit_100.py --sample-size 100
```

### Was prüft der unabhängige 100-Quest-Test?
Im Gegensatz zum internen QA-Loop (der die unkomprimierten Roh-WAVs während der Synthese prüft) inspiziert `07_independent_audit_100.py` die **fertig gemasterten, mit Rassen-Effekten versehenen OGG-Vorbis-Dateien** im Addon-Ausgabeordner:
1. **Akustische & Technische Prüfung (`soundfile` / `ffprobe`):**
   * Gültiger OGG-Vorbis-Container & Abtastrate
   * Keine abgeschnittenen Sätze oder leeren Dateien (Mindestdauer & Sprachaktivitäts-Quote)
   * Kein digitales Übersteuern (Peak-/RMS-Check nach EBU R128 Mastering)
2. **Unabhängige Post-FX Spracherkennung (`Faster-Whisper`):**
   * Transkribiert die fertig gemasterte OGG-Datei erneut und berechnet die Zeichen-Abweichung (**CER**) zum Ziel-Skript.
3. **Qualitäts-Zertifikat & Englischer Community-Hinweis:**
   * Erstellt einen detaillierten Prüfbericht unter `output/qa_reports/independent_audit_100_report.json` (inklusive Gesamtnote **A+ bis F**) und zeigt ihn live im Web-Studio an.
   * Erinnert bei jedem Durchlauf auf Englisch daran, **keine ungeprüften Pakete blind auf CurseForge hochzuladen** und die Arbeit der *Chatty Little NPC*-Entwickler sowie der englischen Community zu respektieren.

---

## 🏗️ Architektur & 7-Stufen-Workflow

```text
wow-chatty-de-pipeline/
├── install.sh                       # 1-Klick System- & Python-.venv-Installer
├── start.py                         # Interaktives Start-Menü (Auswahl für Einsteiger)
├── launch_desktop.sh                # Desktop-Starter (startet Web-Studio & öffnet Browser)
├── run_full_pipeline.sh             # Vollautomatischer Batch-Runner (inkl. 100-Quest Audit)
├── config.yaml                      # Zentrale Konfiguration (Pfade, LUFS, Rassen-FX, QA)
├── pipeline/
│   ├── 01_addon_analyzer.py         # Lua-Parser, Custom-MD5-Hasher & Multi-Thread Wowhead-Scraper
│   ├── 02_voice_extractor.py        # Schneidet & entrauscht 24kHz Mono WAV Voice-Seeds (6-10s)
│   ├── 03_script_agent.py           # Zweistufiges LLM-Routing + Warcraft-Phonetik-Regisseur
│   ├── 04_tts_generator.py          # Lokale CUDA FP16 Batch-Synthese (Coqui XTTS-v2)
│   ├── 05_qa_validator.py           # In-Loop Faster-Whisper ASR + Levenshtein Auto-Re-Synthesis
│   ├── 06_audio_fx.py               # FFmpeg Rassen-DSP, EBU R128 (-16 LUFS) & Addon-Packager
│   └── 07_independent_audit_100.py  # Unabhängiger 100-Quest End-to-End Qualitäts-Prüfer
├── web/
│   ├── index.html                   # A/B-Hörvergleich-Studio + 1-Klick Start-Button Launchpad
│   └── serve.py                     # Lokaler Webserver + Background-Job-Controller (Port 8765)
└── output/
    ├── final_ogg/                   # Gemasterte OGG-Dateien
    ├── qa_reports/                  # JSON-Prüfberichte (In-Loop QA & 100-Quest Audit)
    └── ChattyLittleNpc_<Exp>_deDE_voiceovers/ # Fertiges WoW-Addon für Interface/AddOns/
```

---

## 🤝 Credits & Danksagung

* **Tuubby & das Chatty Little NPC Team** für das großartige World of Warcraft Addon [Chatty Little NPC](https://www.curseforge.com/wow/addons/chatty-little-npc).
* **Die englische Chatty Little NPC Voiceover-Community** für tausende Stunden Arbeit beim Aufnehmen, Kuratieren und Bereitstellen der englischen Original-Sprachpakete, ohne die dieses Stimm-Klon-Projekt nicht möglich wäre.
* **Coqui AI (XTTS-v2)** & **SYSTRAN (Faster-Whisper)** für die lokalen Open-Source-KI-Modelle.
