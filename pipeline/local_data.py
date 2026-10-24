#!/usr/bin/env python3
"""
Lokale WoW-Daten-Anreicherung (pipeline/local_data.py)
------------------------------------------------------
Extrahiert NPC-Metadaten direkt aus der lokalen WoW-Installation
(Creature.db2 über den CASC-Reader) und cacht sie als JSON.

Damit entfallen Wowhead-Lookups für NPC-Namen, wo immer die Daten lokal
vorliegen — weniger Scraping, und die Namen sind offiziell.

Rechtlicher Hinweis: Das Lesen der eigenen, lokal installierten
Spieldateien ist unproblematisch.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cache_file() -> Path:
    return project_root() / "data" / "local" / "npc_names_de.json"


def extract_npc_names(casc) -> Dict[int, Dict[str, str]]:
    """Liest NPC-Namen (deDE) aus Creature.db2. Liefert {npc_id: {name, name2, name3}}."""
    from pipeline.db2_reader import read_db2

    r = read_db2(casc, "dbfilesclient/creature.db2")
    total = r._total_record_data_size
    rs = r.record_size
    out: Dict[int, Dict[str, str]] = {}
    for s in r.sections:
        for i in range(s["record_count"]):
            off = s["file_offset"] + i * rs
            rec = r.buf[off:off + rs]
            rid = r._read_bits(rec, 0, 32)
            f1 = r._read_bits(rec, 32, 32)
            f2 = r._read_bits(rec, 64, 32)
            f3 = r._read_bits(rec, 96, 32)
            name = r.string_table.get(i * rs + 4 + f1 - total, "")
            name2 = r.string_table.get(i * rs + 8 + f2 - total, "")
            name3 = r.string_table.get(i * rs + 12 + f3 - total, "")
            if name or name2 or name3:
                out[rid] = {"name": name, "name2": name2, "name3": name3}
    return out


def load_npc_names(force_refresh: bool = False) -> Dict[int, Dict[str, str]]:
    """NPC-Namen aus dem Cache bzw. aus der lokalen Installation."""
    cf = cache_file()
    if cf.exists() and not force_refresh:
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            return {int(k): v for k, v in data.items()}
        except Exception:
            pass
    try:
        from pipeline.casc_reader import CASCClient, auto_discover_wow_dir
        wow = auto_discover_wow_dir()
        if wow is None:
            return {}
        casc = CASCClient(wow)
        casc.init()
        names = extract_npc_names(casc)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(names, ensure_ascii=False, indent=0), encoding="utf-8")
        return names
    except Exception as e:
        print(f"  Hinweis: lokale NPC-Namen nicht ladbar ({e}) — Fallback: Wowhead/SavedVariables")
        return {}


if __name__ == "__main__":
    names = load_npc_names(force_refresh=True)
    print(f"NPC-Namen geladen: {len(names)}")
    for rid, v in list(names.items())[:10]:
        print(f"  {rid}: {v['name']!r} ({v['name2']!r})")
