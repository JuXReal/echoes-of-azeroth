#!/usr/bin/env python3
"""
Step 1: Addon Analyzer & Multi-Expansion Mapping Builder (01_addon_analyzer.py)
-------------------------------------------------------------------------------
Supports ALL installed ChattyLittleNpc expansions:
  - Midnight (`--expansion Midnight`)
  - The_War_Within (`--expansion The_War_Within`)
  - Dragonflight (`--expansion Dragonflight`)
  - Battle_for_Azeroth (`--expansion Battle_for_Azeroth`)
  - Wrath_of_the_Lich_King (`--expansion Wrath_of_the_Lich_King`)
  - Vanilla (`--expansion Vanilla`)

Capabilities:
1. Parses `VoiceoversList.lua` from the selected expansion pack.
2. Bit-exact Python port of `CLN.MD5:GenerateHash` (`Utils/Md5.lua`) for Gossip,
   GameObject, and Item audio file naming (`<id>_<Type>_<Hash>[_<Gender>].ogg`).
3. Extracts all recorded German (`deDE`) Quest, Gossip, and GameObject texts from
   `SavedVariables/ChattyLittleNpc.lua` (`NpcInfoDB`, `UnitInfoDB`).
4. Optional `--scrape-all-quests` mode: Concurrent, cached scraper for
   `de.wowhead.com` that fetches `Beschreibung` (`Desc`), `Fortschritt` (`Prog`),
   `Vervollständigung` (`Comp`), Quest Titles, and Starter/Ender NPC IDs + Names
   for ALL quests in the expansion pack!
"""

import argparse
import concurrent.futures
import ctypes
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from bs4 import BeautifulSoup, NavigableString, Tag
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.live_state import begin_step, finish_step, increment, log_ai_call, update_current
from pipeline.ai_client import get_settings as get_ai_settings, is_available as ai_is_available, translate_to_german

console = Console()


# ==============================================================================
# ChattyLittleNpc Custom Lua MD5 & Text Cleaning Implementation
# ==============================================================================
CLN_MD5_K = [
    0xD76AA478, 0xE8C7B756, 0x242070DB, 0xC1BDCEEE,
    0xF57C0FAF, 0x4787C62A, 0xA8304613, 0xFD469501,
    0x698098D8, 0x8B44F7AF, 0xFFFF5BB1, 0x895CD7BE,
    0x6B901122, 0xFD987193, 0xA679438E, 0x49B40821,
    0xF61E2562, 0xC040B340, 0x265E5A51, 0xE9B6C7AA,
    0xD62F105D, 0x02441453, 0xD8A1E681, 0xE7D3FBC8,
    0x21E1CDE6, 0xC33707D6, 0xF4D50D87, 0x455A14ED,
    0xA9E3E905, 0xFCEFA3F8, 0x676F02D9, 0x8D2A4C8A,
    0xFFFA3942, 0x8771F681, 0x6D9D6122, 0xFDE5380C,
    0xA4BEEA44, 0x4BDECFA9, 0xF6BB4B60, 0xBEBFBC70,
    0x289B7EC6, 0xEAA127FA, 0xD4EF3085, 0x04881D05,
    0xD9D4D039, 0xE6DB99E5, 0x1FA27CF8, 0xC4AC5665,
    0xF4292244, 0x432AFF97, 0xAB9423A7, 0xFC93A039,
    0x655B59C3, 0x8F0CCC92, 0xFFEFF47D, 0x85845DD1,
    0x6FA87E4F, 0xFE2CE6E0, 0xA3014314, 0x4E0811A1,
    0xF7537E82, 0xBD3AF235, 0x2AD7D2BB, 0xEB86D391,
]


def _to_i32(val: float) -> int:
    return ctypes.c_int32(int(val) & 0xFFFFFFFF).value


def _to_u32(val: float) -> int:
    return ctypes.c_uint32(int(val) & 0xFFFFFFFF).value


def _lrot(x: float, n: int) -> float:
    lsh = _to_i32(_to_u32(x) << (n & 31))
    rsh = _to_i32(_to_u32(x) >> ((32 - n) & 31))
    return float(lsh) + float(rsh)


def generate_cln_lua_md5(message: str) -> str:
    """
    Bit-exact port of CLN.MD5:GenerateHash(message) from ChattyLittleNpc/Utils/Md5.lua.
    Reproduces Lua's exact float64 accumulation and LuaBitOp signed 32-bit shifts.
    """
    data = message.encode("utf-8")
    length = len(data)
    bits = length * 8
    pad_len = 56 - (length + 1) % 64
    if pad_len < 0:
        pad_len += 64
    padding = bytearray([128]) + bytearray(pad_len)
    b_tmp = bits
    for _ in range(8):
        padding.append(b_tmp % 256)
        b_tmp //= 256
    full = data + bytes(padding)

    h0, h1, h2, h3 = float(0x67452301), float(0xEFCDAB89), float(0x98BADCFE), float(0x10325476)
    for offset in range(0, len(full), 64):
        chunk = list(full[offset : offset + 64])
        a, b, c, d = h0, h1, h2, h3
        for i in range(64):
            if i < 16:
                f_val = c
                g_idx = i
            elif i < 32:
                f_val = b
                g_idx = (5 * i + 1) % 16
            elif i < 48:
                f_val = float(_to_i32(_to_i32(b) ^ _to_i32(c) ^ _to_i32(d)))
                g_idx = (3 * i + 5) % 16
            else:
                bor_bd = _to_i32(_to_i32(b) | _to_i32(~_to_i32(d)))
                f_val = float(_to_i32(_to_i32(c) ^ bor_bd))
                g_idx = (7 * i) % 16
            shift_amount = (7, 12, 17, 22)[i % 4]
            temp = d
            d = c
            c = b
            b = b + _lrot(a + f_val + float(CLN_MD5_K[i]) + float(chunk[g_idx]), shift_amount)
            a = temp
        h0 += a
        h1 += b
        h2 += c
        h3 += d

    return f"{_to_u32(h0):08x}{_to_u32(h1):08x}{_to_u32(h2):08x}{_to_u32(h3):08x}"


HTML_CLEAN_PATTERNS = [
    ("\r\n", " "),
    ("<HTML>", ""), ("</HTML>", ""),
    ("<BODY>", ""), ("</BODY>", ""),
    ("<BR/>", ""), ("<p>", ""), ("</p>", ""),
    ('<p align="center">', ""),
]


def load_dotenv_file(project_root: Path) -> None:
    env_file = project_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def clean_text_v1(text: str, player_name: Optional[str] = None, player_class: Optional[str] = None, player_race: Optional[str] = None) -> str:
    """Replicates CLN.Utils:CleanText(text) from Utils/Utils.lua."""
    if not text:
        return ""
    player_name = player_name or os.getenv("WOW_PLAYER_NAME", "Held")
    player_class = player_class or os.getenv("WOW_PLAYER_CLASS", "Paladin")
    player_race = player_race or os.getenv("WOW_PLAYER_RACE", "Blutelf")
    for token in (player_name, player_class, player_race):
        if token:
            for variant in (token, token.lower(), token.upper()):
                text = text.replace(variant, "Hero")
    text = text.replace("\n\n", " ")
    for find_str, repl_str in HTML_CLEAN_PATTERNS:
        text = text.replace(find_str, repl_str)
    return text


def clean_text_v2(text: str, player_name: Optional[str] = None, player_class: Optional[str] = None, player_race: Optional[str] = None) -> str:
    """Replicates CLN.Utils:CleanTextV2(text) from Utils/Utils.lua."""
    if not text:
        return ""
    player_name = player_name or os.getenv("WOW_PLAYER_NAME", "Held")
    player_class = player_class or os.getenv("WOW_PLAYER_CLASS", "Paladin")
    player_race = player_race or os.getenv("WOW_PLAYER_RACE", "Blutelf")
    replacements = [
        (player_name, "name"),
        (player_class, "class"),
        (player_race, "race"),
    ]
    for token, tag in replacements:
        if token:
            for variant in (token, token.lower(), token.upper()):
                text = text.replace(variant, f"{{{tag}|{variant}}}")
    for find_str, repl_str in HTML_CLEAN_PATTERNS:
        text = text.replace(find_str, repl_str)
    return text


def compute_cln_hashes(npc_id: int, text: str) -> List[str]:
    """Replicates CLN.Utils:GetHashes(npcId, text) -> [lua_md5_v1, lua_md5_v2]."""
    t1 = clean_text_v1(text)
    h1 = generate_cln_lua_md5(f"{npc_id}{t1}")
    t2 = clean_text_v2(text)
    h2 = generate_cln_lua_md5(f"{npc_id}{t2}")
    return [h1, h2]


def strip_stage_directions_and_placeholders(text: str, spoken_player_title: str = "Champion") -> Tuple[str, List[str]]:
    """
    Removes stage directions like <Arator brodelt vor Zorn.> from spoken dialogue
    (while extracting them as acting cues for the LLM director) and resolves
    {name|...} / {class|...} placeholders for natural German speech.
    """
    stage_cues = re.findall(r"<([^>]+)>", text)
    spoken = re.sub(r"<[^>]+>", " ", text)
    spoken = re.sub(r"\{name\|[^}]+\}", spoken_player_title, spoken)
    spoken = re.sub(r"\{class\|[^}]+\}", spoken_player_title, spoken)
    spoken = re.sub(r"\{race\|[^}]+\}", spoken_player_title, spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken, stage_cues


# ==============================================================================
# Known Lore NPC Race & Archetype Enrichment
# ==============================================================================
KNOWN_NPC_ARCHETYPES = {
    235787: {"race": "Blood Elf", "archetype": "lore_lorthemar_theron", "role": "Lordregent von Quel'Thalas (Tief, majestätisch, autoritär)"},
    263465: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    258020: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    258029: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    258022: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    258150: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    261878: {"race": "Blood Elf", "archetype": "lore_arator", "role": "Arator der Erlöser (Halbelf-Paladin, entschlossen, emotional)"},
    258019: {"race": "Void Elf", "archetype": "lore_magister_umbric", "role": "Magister Umbric (Anführer der Leerenelfen, analytisch, ruhig, mystisch)"},
    258151: {"race": "Void Elf", "archetype": "lore_magister_umbric", "role": "Magister Umbric (Anführer der Leerenelfen, analytisch, ruhig, mystisch)"},
    258021: {"race": "Void Elf", "archetype": "lore_magister_umbric", "role": "Magister Umbric (Anführer der Leerenelfen, analytisch, ruhig, mystisch)"},
    262269: {"race": "Void Elf", "archetype": "lore_magister_umbric", "role": "Magister Umbric (Anführer der Leerenelfen, analytisch, ruhig, mystisch)"},
    258538: {"race": "Void Elf", "archetype": "lore_magister_umbric", "role": "Magister Umbric (Anführer der Leerenelfen, analytisch, ruhig, mystisch)"},
    262969: {"race": "Blood Elf", "archetype": "lore_lady_liadrin", "role": "Lady Liadrin (Matriarchin der Blutritter, edel, kämpferisch)"},
    262944: {"race": "Blood Elf", "archetype": "lore_halduron", "role": "Halduron Wolkenglanz (Waldläufergeneral von Silbermond)"},
    258024: {"race": "Entartung", "archetype": "creature_void_wretch", "role": "Erbärmliches Leerenekel (Verängstigte Leerenkreatur, zischend, flehend)"},
    262880: {"race": "Troll", "archetype": "lore_erinye", "role": "Er'inye, Giftgelehrte von Atal'Utek (Geisthexe der Amani, düster, verführerisch)"},
    272056: {"race": "Troll", "archetype": "lore_erinye", "role": "Er'inye, Giftgelehrte von Atal'Utek (Geisthexe der Amani, düster, verführerisch)"},
    262798: {"race": "Troll", "archetype": "lore_abdumati", "role": "Kriegsanführer Abdumati (Amani-Kriegsherr, rau, kriegerisch, tief)"},
    259416: {"race": "Troll", "archetype": "lore_zuljarra", "role": "Zul'jarra (Amani-Anführerin, ernst, erschöpft)"},
    272197: {"race": "Undead", "archetype": "undead_amani_windcaller", "role": "Windrufer der Amani (Untoter Troll-Geist, hallend, mystisch)"},
    258755: {"race": "Troll", "archetype": "npc_captain_tokka", "role": "Käpt'n Tokka (Seebär, rau, entschlossen)"},
    264258: {"race": "Blood Elf", "archetype": "bloodelf_female_farstrider", "role": "Rekrutin der Weltenwanderer (Aufmerksam, pflichtbewusst)"},
}


def infer_race_from_name_or_zone(npc_name: str, zone: str = "") -> str:
    """Heuristic fallback to assign Race-FX for scraped quests when NPC isn't in SavedVariables yet."""
    low = f"{npc_name} {zone}".lower()
    if any(k in low for k in ("umbric", "leeren", "void", "rissanbeter", "alleria")):
        return "Void Elf"
    if any(k in low for k in ("zul'", "amani", "atal'", "loa", "troll", "halazzi", "nalorakk", "akil'zon", "jan'alai")):
        return "Troll"
    if any(k in low for k in ("untot", "geißel", "geist", "knochen", "gruft", "todesritter", "lich")):
        return "Undead"
    if any(k in low for k in ("tauren", "mulgore", "donnerfels", "haranir")):
        return "Tauren"
    if any(k in low for k in ("gnom", "mechagnom", "tüftler")):
        return "Gnome"
    if any(k in low for k in ("goblin", "bilgewasser", "kezan")):
        return "Goblin"
    if any(k in low for k in ("silbermond", "immersang", "quel'", "lor'themar", "liadrin", "halduron", "arator", "magister", "weltenwanderer", "blutritter")):
        return "Blood Elf"
    return "Default"


def parse_voiceovers_list(vo_list_path: Path) -> Tuple[List[str], Dict[str, float]]:
    """Parses VoiceoversList.lua from any ChattyLittleNpc_<Expansion>_voiceovers pack."""
    content = vo_list_path.read_text(encoding="utf-8")
    files = re.findall(r"'([^']+\.(?:ogg|mp3))'", content)
    durations = {}
    for m in re.finditer(r'\["([^"]+)"\]\s*=\s*([0-9.]+)', content):
        durations[m.group(1)] = float(m.group(2))
    return files, durations


# ==============================================================================
# Wowhead DE Full Quest Scraper (Title + Desc + Prog + Comp + Starter/Ender NPC)
# ==============================================================================
def sanitize_wowhead_text(title: str) -> str:
    """Entfernt Wowhead-Markup/JSON-Reste aus Quest-Titeln."""
    t = re.sub(r"\s*\|.*$", "", title)          # "Titel | .","date":..." -> "Titel"
    t = re.sub(r'\.\s*"date".*$', "", t)        # eingebettete Kommentar-JSON-Reste
    return t.strip()[:200]


def fetch_wowhead_de_quest_full(quest_id: int, domain: str = "www.wowhead.com/de") -> Dict:
    """
    Scrapes a German quest page (`https://www.wowhead.com/de/quest=<id>`) for:
      - title
      - Desc (`Beschreibung`)
      - Prog (`Fortschritt`)
      - Comp (`Vervollständigung`)
      - start_npc_id, start_npc_name
      - end_npc_id, end_npc_name
    """
    result = {
        "quest_id": quest_id,
        "title": f"Quest #{quest_id}",
        "Desc": "",
        "Prog": "",
        "Comp": "",
        "start_npc_id": 0,
        "start_npc_name": "Unbekannter NPC",
        "end_npc_id": 0,
        "end_npc_name": "Unbekannter NPC",
    }
    try:
        url = f"https://{domain}/quest={quest_id}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}, timeout=8)
        if resp.status_code != 200:
            return result
        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1", class_="heading-size-1")
        if h1 and h1.text:
            result["title"] = sanitize_wowhead_text(h1.text)

        # Extract Starter & Ender NPC from Wowhead markup (`[url=/de/npc=258019/magister-umbric]Magister Umbric[/url]`)
        npc_links = re.findall(r"npc=(\d+)(?:\\?/[^\]\">]+)?[\]\">]([^\[<]+)", html)
        if npc_links:
            result["start_npc_id"] = int(npc_links[0][0])
            result["start_npc_name"] = sanitize_wowhead_text(npc_links[0][1])
            if len(npc_links) >= 2:
                result["end_npc_id"] = int(npc_links[1][0])
                result["end_npc_name"] = sanitize_wowhead_text(npc_links[1][1])
            else:
                result["end_npc_id"] = result["start_npc_id"]
                result["end_npc_name"] = result["start_npc_name"]

        # Extract Beschreibung, Fortschritt, Vervollständigung
        # (DE-Seiten deutsch, EN-Seiten englisch — beide Varianten matchen)
        section_map = {
            "Beschreibung": "Desc",
            "Fortschritt": "Prog",
            "Vervollständigung": "Comp",
            "Description": "Desc",
            "Progress": "Prog",
            "Completion": "Comp",
        }
        for h2 in soup.find_all("h2", class_="heading-size-3"):
            sec_title = h2.get_text(strip=True)
            if sec_title not in section_map:
                continue
            phase_key = section_map[sec_title]
            parts = []
            curr = h2.next_sibling
            while curr:
                if isinstance(curr, Tag) and curr.name in ("h2", "h3", "script", "style", "table", "ul"):
                    if curr.name in ("h2", "h3"):
                        break
                elif isinstance(curr, NavigableString):
                    t = str(curr).strip()
                    if t:
                        parts.append(t)
                elif isinstance(curr, Tag):
                    classes = curr.get("class") or []
                    if "box" not in classes and "pad" not in classes:
                        t = curr.get_text(" ", strip=True)
                        if t and "C_QuestLog.IsQuestFlaggedCompleted" not in t:
                            parts.append(t)
                curr = curr.next_sibling
            joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
            result[phase_key] = joined
    except Exception:
        pass
    return result


def parse_saved_variables(
    sv_path: Path,
    vo_dir: Path,
    durations: Dict[str, float],
    include_gossip: bool = False,
) -> List[Dict]:
    """
    Extracts all recorded German quests, gossips, and gameobject texts from
    SavedVariables/ChattyLittleNpc.lua that have matching English reference audio in `vo_dir`.
    """
    if not sv_path.exists():
        console.print(f"[yellow]Warning: SavedVariables not found at {sv_path}[/yellow]")
        return []

    sv_content = sv_path.read_text(encoding="utf-8")
    npc_section = sv_content.split("UnitInfoDB =")[0]
    npc_blocks = re.split(r'\n\[(\d+)\]\s*=\s*\{\s*\n\["deDE"\]', npc_section)

    entries = []
    for i in range(1, len(npc_blocks), 2):
        npc_id = int(npc_blocks[i])
        block = npc_blocks[i + 1]

        name_m = re.search(r'\["name"\]\s*=\s*"([^"]*)"', block)
        race_m = re.search(r'\["race"\]\s*=\s*"([^"]*)"', block)
        sex_m = re.search(r'\["sex"\]\s*=\s*"([^"]*)"', block)
        zone_m = re.search(r'\["zone"\]\s*=\s*"([^"]*)"', block)
        subzone_m = re.search(r'\["subzone"\]\s*=\s*"([^"]*)"', block)
        ctype_m = re.search(r'\["creatureType"\]\s*=\s*"([^"]*)"', block)
        model_m = re.search(r'\["modelFileId"\]\s*=\s*(\d+)', block)

        name = name_m.group(1) if name_m else f"NPC_{npc_id}"
        race = race_m.group(1) if race_m else ""
        sex = sex_m.group(1) if sex_m else "Neutral"
        zone = zone_m.group(1) if zone_m else "Quel'Thalas"
        subzone = subzone_m.group(1) if subzone_m else ""
        ctype = ctype_m.group(1) if ctype_m else "Humanoid"
        model_id = int(model_m.group(1)) if model_m else None

        meta = KNOWN_NPC_ARCHETYPES.get(npc_id, {})
        if not race:
            race = meta.get(
                "race",
                "Undead" if ctype == "Untoter" else ("Entartung" if ctype == "Entartung" else infer_race_from_name_or_zone(name, zone)),
            )
        archetype = meta.get("archetype", f"{race.lower().replace(' ', '_')}_{sex.lower()}")
        role_desc = meta.get("role", f"{name} ({race}, {sex})")

        # 1. Extract Quests
        q_matches = re.finditer(
            r'\[(\d+)\]\s*=\s*\{\s*\["quest_detail"\]\s*=\s*"((?:[^"\\]|\\.)*)",\s*\["quest_progress"\]\s*=\s*"((?:[^"\\]|\\.)*)",\s*\["quest_complete"\]\s*=\s*"((?:[^"\\]|\\.)*)"',
            block,
        )
        for qm in q_matches:
            quest_id = int(qm.group(1))
            phases = {
                "Desc": qm.group(2).replace('\\"', '"'),
                "Prog": qm.group(3).replace('\\"', '"'),
                "Comp": qm.group(4).replace('\\"', '"'),
            }
            for phase, raw_text in phases.items():
                if not raw_text.strip():
                    continue
                target_filename = f"{quest_id}_{phase}.ogg"
                source_ogg = vo_dir / target_filename
                if not source_ogg.exists():
                    continue

                spoken_text, stage_cues = strip_stage_directions_and_placeholders(raw_text)
                entries.append({
                    "entry_id": f"{quest_id}_{phase}",
                    "kind": "quest",
                    "quest_id": quest_id,
                    "phase": phase,
                    "npc_id": npc_id,
                    "npc_name": name,
                    "race": race,
                    "gender": sex,
                    "creature_type": ctype,
                    "zone": zone,
                    "subzone": subzone,
                    "model_file_id": model_id,
                    "voice_archetype": archetype,
                    "role_description": role_desc,
                    "source_ogg_filename": target_filename,
                    "source_ogg_path": str(source_ogg),
                    "source_duration_sec": durations.get(target_filename, 0.0),
                    "target_ogg_filename": target_filename,
                    "raw_de_text": raw_text,
                    "clean_de_text": spoken_text,
                    "stage_directions": stage_cues,
                })

        # 2. Extract Gossip (if enabled)
        if include_gossip:
            gossip_matches = re.findall(r'\["([0-9a-f]{32}_[A-Za-z]+)"\]\s*=\s*"((?:[^"\\]|\\.)*)"', block)
            en_gossips = sorted(vo_dir.glob(f"{npc_id}_Gossip_*.ogg"))
            if gossip_matches and en_gossips:
                # Pick longest English gossip file of that NPC as voice reference
                best_en_ogg = max(en_gossips, key=lambda p: durations.get(p.name, 0.0))
                for g_hash_gender, raw_g_text in gossip_matches:
                    raw_g_text = raw_g_text.replace('\\"', '"')
                    if not raw_g_text.strip():
                        continue
                    target_g_filename = f"{npc_id}_Gossip_{g_hash_gender}.ogg"
                    spoken_text, stage_cues = strip_stage_directions_and_placeholders(raw_g_text)
                    entries.append({
                        "entry_id": f"{npc_id}_Gossip_{g_hash_gender[:8]}",
                        "kind": "gossip",
                        "quest_id": npc_id,
                        "phase": "Gossip",
                        "npc_id": npc_id,
                        "npc_name": name,
                        "race": race,
                        "gender": sex,
                        "creature_type": ctype,
                        "zone": zone,
                        "subzone": subzone,
                        "model_file_id": model_id,
                        "voice_archetype": archetype,
                        "role_description": role_desc,
                        "source_ogg_filename": best_en_ogg.name,
                        "source_ogg_path": str(best_en_ogg),
                        "source_duration_sec": durations.get(best_en_ogg.name, 0.0),
                        "target_ogg_filename": target_g_filename,
                        "raw_de_text": raw_g_text,
                        "clean_de_text": spoken_text,
                        "stage_directions": stage_cues,
                    })

    return entries


def scrape_missing_pack_quests(
    files: List[str],
    vo_dir: Path,
    durations: Dict[str, float],
    existing_entries: List[Dict],
    cache_file: Path,
    max_workers: int = 6,  # bewusst moderat (Wowhead-Höflichkeit)
    ai_settings: Optional[Dict] = None,
    en_cache_file: Optional[Path] = None,
    trans_cache_file: Optional[Path] = None,
    local_names: Optional[Dict[int, Dict[str, str]]] = None,
) -> List[Dict]:
    """
    Scrapes German quest texts (Desc, Prog, Comp) from de.wowhead.com for all
    `<QuestID>_<Phase>.ogg` files in the expansion pack that aren't in SavedVariables yet.
    Fehlt der deutsche Text, wird er optional vom englischen Wowhead geholt und
    per KI ins Deutsche übersetzt (ai_settings + translate_missing_quests).
    """
    existing_keys = {e["target_ogg_filename"] for e in existing_entries}
    quest_files = [f for f in files if re.match(r"^\d+_(Desc|Prog|Comp)\.ogg$", f) and f not in existing_keys]
    needed_qids = sorted({int(f.split("_")[0]) for f in quest_files})

    cache: Dict[str, Dict] = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    to_fetch = [qid for qid in needed_qids if str(qid) not in cache]
    if to_fetch:
        console.print(f"[cyan]• Scraping {len(to_fetch)} missing quests from de.wowhead.com ({max_workers} threads, gecacht)...[/cyan]")
        begin_step("analyze", total=len(to_fetch))
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}% ({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[green]Fetching Wowhead DE Quests...", total=len(to_fetch))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_qid = {pool.submit(fetch_wowhead_de_quest_full, qid): qid for qid in to_fetch}
                for idx, fut in enumerate(concurrent.futures.as_completed(future_to_qid), 1):
                    qid = future_to_qid[fut]
                    try:
                        cache[str(qid)] = fut.result()
                    except Exception:
                        pass
                    progress.advance(task)
                    update_current({
                        "entry_id": f"scrape:{qid}",
                        "npc_name": "Wowhead",
                        "quest_title_de": f"Quest #{qid}",
                        "phase": "Scrape",
                        "status": "scraping",
                        "cer": None,
                    })
                    increment(processed=1)
                    if idx % 100 == 0:
                        cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

        cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- KI-Übersetzung für Quests ohne deutschen Text ---
    en_cache: Dict[str, Dict] = {}
    trans_cache: Dict[str, Dict] = {}
    translate = bool(ai_settings and ai_is_available(ai_settings) and en_cache_file and trans_cache_file)
    if translate:
        for cf in (en_cache_file, trans_cache_file):
            if cf.exists():
                try:
                    if cf == en_cache_file:
                        en_cache = json.loads(cf.read_text(encoding="utf-8"))
                    else:
                        trans_cache = json.loads(cf.read_text(encoding="utf-8"))
                except Exception:
                    pass
        missing_de = [
            qid for qid in needed_qids
            if not (cache.get(str(qid)) or {}).get("Desc", "").strip()
            and not (cache.get(str(qid)) or {}).get("Prog", "").strip()
            and not (cache.get(str(qid)) or {}).get("Comp", "").strip()
        ]
        if missing_de:
            console.print(f"[magenta]• Übersetze {len(missing_de)} Quests ohne deutschen Text via KI ({ai_settings['provider']})...[/magenta]")
            begin_step("analyze", total=len(missing_de))
            for idx, qid in enumerate(missing_de, 1):
                qid_str = str(qid)
                update_current({
                    "entry_id": f"translate:{qid}",
                    "npc_name": "DeepSeek",
                    "quest_title_de": f"Quest #{qid}",
                    "phase": "Übersetzung",
                    "status": "translating",
                    "cer": None,
                })
                increment(processed=1)
                if qid_str not in trans_cache:
                    en = en_cache.get(qid_str)
                    if en is None:
                        en = fetch_wowhead_de_quest_full(qid, domain="www.wowhead.com")
                        en_cache[qid_str] = en
                    tdata = {"title": None, "Desc": None, "Prog": None, "Comp": None,
                             "start_npc_id": en.get("start_npc_id", 0), "start_npc_name": en.get("start_npc_name", "NPC"),
                             "end_npc_id": en.get("end_npc_id", 0), "end_npc_name": en.get("end_npc_name", "NPC")}
                    title = (en.get("title") or "").strip()
                    if title and not title.startswith("Quest #"):
                        t, note, usage = translate_to_german(ai_settings, title)
                        if t:
                            tdata["title"] = t
                            log_ai_call(ai_settings["provider"], ai_settings["model"], f"{qid}_Title", note, ok=True, tokens=usage, cost_usd=usage.get("cost_usd", 0.0))
                    for phase in ("Desc", "Prog", "Comp"):
                        txt = (en.get(phase) or "").strip()
                        if not txt:
                            continue
                        t, note, usage = translate_to_german(ai_settings, txt)
                        if t:
                            tdata[phase] = t
                            log_ai_call(ai_settings["provider"], ai_settings["model"], f"{qid}_{phase}", note, ok=True, tokens=usage, cost_usd=usage.get("cost_usd", 0.0))
                    # Nur cachen, wenn wirklich etwas übersetzt wurde — sonst
                    # beim nächsten Lauf erneut versuchen
                    if any((tdata.get(k) or "").strip() for k in ("Desc", "Prog", "Comp", "title")):
                        trans_cache[qid_str] = tdata
                if idx % 50 == 0 or idx == len(missing_de):
                    trans_cache_file.write_text(json.dumps(trans_cache, indent=2, ensure_ascii=False), encoding="utf-8")
                    en_cache_file.write_text(json.dumps(en_cache, indent=2, ensure_ascii=False), encoding="utf-8")

    scraped_entries = []
    for fname in quest_files:
        qid_str, phase_ext = fname.split("_", 1)
        qid = int(qid_str)
        phase = phase_ext.replace(".ogg", "")
        qdata = cache.get(qid_str)
        translated_by_ai = False
        if (not qdata or not (qdata.get(phase) or "").strip()) and translate:
            tdata = trans_cache.get(qid_str) or {}
            if tdata.get(phase):
                qdata = {
                    "title": tdata.get("title") or f"Quest #{qid}",
                    "Desc": tdata.get("Desc") or "",
                    "Prog": tdata.get("Prog") or "",
                    "Comp": tdata.get("Comp") or "",
                    "start_npc_id": tdata.get("start_npc_id", 0),
                    "start_npc_name": tdata.get("start_npc_name", "NPC"),
                    "end_npc_id": tdata.get("end_npc_id", 0),
                    "end_npc_name": tdata.get("end_npc_name", "NPC"),
                }
                translated_by_ai = True
        if not qdata:
            continue
        raw_text = (qdata.get(phase) or "").strip()
        if not raw_text:
            continue

        npc_id = qdata.get("start_npc_id", 0) if phase == "Desc" else qdata.get("end_npc_id", 0)
        npc_name = qdata.get("start_npc_name", "NPC") if phase == "Desc" else qdata.get("end_npc_name", "NPC")
        npc_name_source = "wowhead"
        # Lokale DB2-Namen bevorzugen (offiziell, kein Scraping)
        if local_names and npc_id and npc_id in local_names:
            local_entry = local_names[npc_id]
            local_name = (local_entry.get("name") or local_entry.get("name2") or "").strip()
            if local_name:
                npc_name = local_name
                npc_name_source = "local_db2"
        meta = KNOWN_NPC_ARCHETYPES.get(npc_id, {})
        race = meta.get("race") or infer_race_from_name_or_zone(npc_name)
        archetype = meta.get("archetype", f"npc_{npc_id}" if npc_id else f"quest_{qid}")
        spoken_text, stage_cues = strip_stage_directions_and_placeholders(raw_text)
        if not spoken_text:
            continue

        entry = {
            "entry_id": f"{qid}_{phase}",
            "kind": "quest",
            "quest_id": qid,
            "quest_title_de": qdata.get("title", f"Quest #{qid}"),
            "phase": phase,
            "npc_id": npc_id,
            "npc_name": npc_name,
            "npc_name_source": npc_name_source,
            "race": race,
            "gender": "Neutral",
            "creature_type": "Humanoid",
            "zone": "Azeroth / Quel'Thalas",
            "subzone": "",
            "model_file_id": None,
            "voice_archetype": archetype,
            "role_description": f"{npc_name} ({race})",
            "source_ogg_filename": fname,
            "source_ogg_path": str(vo_dir / fname),
            "source_duration_sec": durations.get(fname, 0.0),
            "target_ogg_filename": fname,
            "raw_de_text": raw_text,
            "clean_de_text": spoken_text,
            "stage_directions": stage_cues,
        }
        if translated_by_ai:
            entry["translated_by_ai"] = True
        scraped_entries.append(entry)

    return scraped_entries


def fetch_wowhead_de_quest_title(quest_id: int, cache: Dict[int, str]) -> str:
    """Fetches the official German quest title from Wowhead DE (with local caching)."""
    if quest_id in cache:
        return cache[quest_id]
    try:
        url = f"https://{domain}/quest={quest_id}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            h1 = soup.find("h1", class_="heading-size-1")
            if h1 and h1.text:
                title = sanitize_wowhead_text(h1.text)
                cache[quest_id] = title
                return title
    except Exception:
        pass
    fallback = f"Quest #{quest_id}"
    cache[quest_id] = fallback
    return fallback


def select_benchmark_entries(entries: List[Dict], limit: int = 20) -> List[Dict]:
    """Selects diverse, lore-rich quest voiceovers for a pilot run, or all if limit == 0."""
    if limit <= 0 or limit >= len(entries):
        return sorted(entries, key=lambda x: (x["quest_id"], x["phase"]))

    scored = []
    seen_npcs = {}
    for e in entries:
        text_len = len(e["clean_de_text"])
        dur = e["source_duration_sec"]
        arch = e["voice_archetype"]
        npc_count = seen_npcs.get(arch, 0)
        length_score = 100 if (80 <= text_len <= 460) else (60 if text_len > 460 else 40)
        dur_score = 50 if dur >= 6.0 else 20
        diversity_bonus = max(0, 50 - npc_count * 12)
        total_score = length_score + dur_score + diversity_bonus
        scored.append((total_score, e))
        seen_npcs[arch] = npc_count + 1

    scored.sort(key=lambda x: (-x[0], x[1]["quest_id"], x[1]["phase"]))
    selected = [item[1] for item in scored[:limit]]
    selected.sort(key=lambda x: (x["quest_id"], x["phase"]))
    return selected


def main():
    parser = argparse.ArgumentParser(description="Step 1: Analyze ChattyLittleNpc & build DE mapping for any expansion.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--expansion", default=None, help="Expansion name (e.g. Midnight, The_War_Within, Dragonflight, Vanilla)")
    parser.add_argument("--limit", type=int, default=None, help="Override pilot_limit (0 = all entries)")
    parser.add_argument("--include-gossip", action="store_true", help="Include recorded German Gossip lines from SavedVariables")
    parser.add_argument("--scrape-all-quests", action="store_true", help="Scrape all missing quest texts for this expansion from de.wowhead.com")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    load_dotenv_file(project_root)
    cfg_path = project_root / args.config
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    expansion = args.expansion or cfg["project"].get("expansion", "Midnight")
    wow_addons_dir = Path(os.getenv("WOW_ADDONS_DIR") or cfg["paths"]["wow_addons_dir"])
    source_pack_dir = wow_addons_dir / f"ChattyLittleNpc_{expansion}_voiceovers"
    if not source_pack_dir.exists():
        source_pack_dir = Path(cfg["paths"]["source_pack_dir"])

    target_addon_name = f"ChattyLittleNpc_{expansion}_deDE_voiceovers"
    pilot_limit = args.limit if args.limit is not None else cfg["project"].get("pilot_limit", 20)
    vo_list_path = source_pack_dir / "VoiceoversList.lua"
    vo_dir = source_pack_dir / "voiceovers"
    sv_path = Path(os.getenv("WOW_SAVED_VARS") or cfg["paths"]["saved_variables_lua"])

    console.rule(f"[bold cyan]Step 1: ChattyLittleNpc Addon Analyzer ({expansion} -> {target_addon_name})[/bold cyan]")
    begin_step("analyze", total=0, expansion=expansion)

    files, durations = parse_voiceovers_list(vo_list_path)
    quest_ogg_count = sum(1 for x in files if re.match(r"^\d+_(Desc|Prog|Comp)\.ogg$", x))
    gossip_ogg_count = sum(1 for x in files if "_Gossip_" in x)
    other_ogg_count = len(files) - quest_ogg_count - gossip_ogg_count

    console.print(f"• Source Addon Pack: [bold]{source_pack_dir.name}[/bold]")
    console.print(f"• Total {expansion} Audio Files: [green]{len(files)}[/green] "
                  f"(Quests: {quest_ogg_count}, Gossip: {gossip_ogg_count}, Greeting/Obj/Item: {other_ogg_count})")

    orig_link = project_root / cfg["paths"]["data_original"] / f"{expansion.lower()}_voiceovers"
    orig_link.parent.mkdir(parents=True, exist_ok=True)
    if not orig_link.exists() and vo_dir.exists():
        os.symlink(vo_dir, orig_link)

    all_de_entries = parse_saved_variables(sv_path, vo_dir, durations, include_gossip=args.include_gossip)
    console.print(f"• Extracted [bold green]{len(all_de_entries)}[/bold green] verified German (deDE) entries from SavedVariables.")

    raw_de_dir = project_root / cfg["paths"]["data_raw_de_text"]
    raw_de_dir.mkdir(parents=True, exist_ok=True)

    # Fetch titles for SavedVariables entries
    title_cache_path = raw_de_dir / "quest_titles_cache.json"
    title_cache = {}
    if title_cache_path.exists():
        title_cache = {int(k): v for k, v in json.loads(title_cache_path.read_text(encoding="utf-8")).items()}

    for entry in all_de_entries:
        if entry["kind"] == "quest":
            entry["quest_title_de"] = fetch_wowhead_de_quest_title(entry["quest_id"], title_cache)
        else:
            entry["quest_title_de"] = f"Gossip: {entry['npc_name']}"

    title_cache_path.write_text(json.dumps(title_cache, indent=2, ensure_ascii=False), encoding="utf-8")

    # Optional: Scrape all remaining expansion quests from de.wowhead.com
    if args.scrape_all_quests:
        wowhead_cache_file = raw_de_dir / f"wowhead_{expansion.lower()}_quests_cache.json"
        en_cache_file = raw_de_dir / f"wowhead_{expansion.lower()}_quests_en_cache.json"
        trans_cache_file = raw_de_dir / f"quest_translations_{expansion.lower()}_cache.json"
        try:
            ai_settings = get_ai_settings(cfg)
            if not (cfg.get("ai", {}).get("translate_missing_quests", True)):
                ai_settings = None
        except Exception:
            ai_settings = None
        # Lokale NPC-Namen aus Creature.db2 (reduziert Wowhead-Abhängigkeit)
        local_names = None
        try:
            from pipeline.local_data import load_npc_names
            local_names = load_npc_names()
            if local_names:
                console.print(f"[green]• Lokale NPC-Namen aus Creature.db2 geladen: {len(local_names)}[/green]")
        except Exception:
            local_names = None
        scraped = scrape_missing_pack_quests(
            files, vo_dir, durations, all_de_entries, wowhead_cache_file,
            ai_settings=ai_settings,
            en_cache_file=en_cache_file,
            trans_cache_file=trans_cache_file,
            local_names=local_names,
        )
        console.print(f"• Scraped [bold green]{len(scraped)}[/bold green] additional German quest phases from de.wowhead.com!")
        all_de_entries.extend(scraped)

    selected_entries = select_benchmark_entries(all_de_entries, limit=pilot_limit)

    full_catalog_path = raw_de_dir / "midnight_de_full_catalog.json"
    pilot_catalog_path = raw_de_dir / "midnight_de_pilot_20.json"

    addon_schema_report = {
        "addon_architecture": {
            "expansion": expansion,
            "pack_naming_convention": "ChattyLittleNpc_<Expansion>_<locale>_voiceovers",
            "target_pack_name": target_addon_name,
            "quest_lookup_pattern": "<questId>_<Desc|Prog|Comp>.ogg",
            "gossip_lookup_pattern": "<npcId>_<Gossip|GameObject|Item>_<MD5(npcId + CleanText(de_text))>[_<Male|Female|Neutral>].ogg",
            "greeting_lookup_pattern": "<npcId>_QuestGreeting.ogg",
            "fallback_mechanism": "CLN:IterateVoiceoverPacks() prioritizes active deDE pack, then falls back to enUS pack per file.",
        },
        "statistics": {
            "total_en_files": len(files),
            "quest_en_files": quest_ogg_count,
            "gossip_en_files": gossip_ogg_count,
            "verified_de_quest_entries": len(all_de_entries),
            "selected_pilot_entries": len(selected_entries),
        },
        "entries": selected_entries,
    }

    full_catalog_path.write_text(json.dumps(all_de_entries, indent=2, ensure_ascii=False), encoding="utf-8")
    pilot_catalog_path.write_text(json.dumps(addon_schema_report, indent=2, ensure_ascii=False), encoding="utf-8")

    table = Table(title=f"Selected {len(selected_entries)} {expansion} Entries for Active Batch (deDE)")
    table.add_column("#", justify="right", style="dim")
    table.add_column("File", style="cyan")
    table.add_column("Quest / Entry Title (DE)", style="bold white")
    table.add_column("NPCSpeaker", style="green")
    table.add_column("Race / FX", style="magenta")
    table.add_column("EN Dur", justify="right")
    table.add_column("DE Chars", justify="right")

    for idx, item in enumerate(selected_entries[:30], 1):
        table.add_row(
            str(idx),
            item["target_ogg_filename"],
            item["quest_title_de"],
            item["npc_name"],
            item["race"],
            f"{item['source_duration_sec']:.1f}s",
            str(len(item["clean_de_text"])),
        )

    console.print(table)
    if len(selected_entries) > 30:
        console.print(f"[dim]... and {len(selected_entries) - 30} more entries in {pilot_catalog_path.name}[/dim]")
    console.print(f"[bold green]✓ Saved mapping catalog ({len(selected_entries)} active entries) -> {pilot_catalog_path}[/bold green]")
    finish_step(ok=True)


if __name__ == "__main__":
    main()
