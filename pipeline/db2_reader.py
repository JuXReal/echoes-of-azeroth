#!/usr/bin/env python3
"""
WDC5/DB2-Parser für die lokalen WoW-Daten (pipeline/db2_reader.py)
-------------------------------------------------------------------
Parst WDC5-Dateien (Spaltenlayout + Storage-Typen direkt aus dem Header)
und extrahiert deutsche Texte aus BroadcastText & Co.

Referenz: LiangYuxuan/wow-casc-dbc (wdc.ts, MIT).
"""

import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STORAGE_NONE = 0
STORAGE_BITPACKED = 1
STORAGE_COMMON_DATA = 2
STORAGE_BITPACKED_INDEXED = 3
STORAGE_BITPACKED_INDEXED_ARRAY = 4
STORAGE_BITPACKED_SIGNED = 5


class WDC5Reader:
    def __init__(self, buf: bytes):
        assert buf[:4] == b"WDC5", f"Kein WDC5-Magic: {buf[:4]!r}"
        self.buf = buf
        self.version = struct.unpack_from("<I", buf, 4)[0]
        self.record_count = struct.unpack_from("<I", buf, 136)[0]
        self.field_count = struct.unpack_from("<I", buf, 140)[0]
        self.record_size = struct.unpack_from("<I", buf, 144)[0]
        self.table_hash = struct.unpack_from("<I", buf, 152)[0]
        self.locale = struct.unpack_from("<I", buf, 168)[0]
        self.flags = struct.unpack_from("<H", buf, 172)[0]
        self.id_index = struct.unpack_from("<H", buf, 174)[0]
        self.field_storage_info_size = struct.unpack_from("<I", buf, 188)[0]
        self.common_data_size = struct.unpack_from("<I", buf, 192)[0]
        self.pallet_data_size = struct.unpack_from("<I", buf, 196)[0]
        self.section_count = struct.unpack_from("<I", buf, 200)[0]
        self.is_normal = not (self.flags & 0x1)

        # Sektionen
        self.sections = []
        for i in range(self.section_count):
            off = 204 + i * 40
            self.sections.append({
                "tact_key_hash": struct.unpack_from("<Q", buf, off)[0],
                "file_offset": struct.unpack_from("<I", buf, off + 8)[0],
                "record_count": struct.unpack_from("<I", buf, off + 12)[0],
                "string_table_size": struct.unpack_from("<I", buf, off + 16)[0],
                "offset_records_end": struct.unpack_from("<I", buf, off + 20)[0],
                "id_list_size": struct.unpack_from("<I", buf, off + 24)[0],
                "relationship_size": struct.unpack_from("<I", buf, off + 28)[0],
                "offset_map_count": struct.unpack_from("<I", buf, off + 32)[0],
                "copy_table_count": struct.unpack_from("<I", buf, off + 36)[0],
            })

        # Feld-Storage-Info
        fields_offset = 204 + self.section_count * 40
        self.field_offsets: List[Tuple[int, int]] = []  # (position, size) aus dem Header
        for i in range(self.field_count):
            off = fields_offset + i * 4
            size = struct.unpack_from("<h", buf, off)[0]
            pos = struct.unpack_from("<H", buf, off + 2)[0]
            self.field_offsets.append((pos, size))

        info_offset = fields_offset + self.field_count * 4
        self.field_info: List[Dict] = []
        for i in range(self.field_storage_info_size // 24):
            off = info_offset + i * 24
            self.field_info.append({
                "offset_bits": struct.unpack_from("<H", buf, off)[0],
                "size_bits": struct.unpack_from("<H", buf, off + 2)[0],
                "additional_data_size": struct.unpack_from("<I", buf, off + 4)[0],
                "storage_type": struct.unpack_from("<I", buf, off + 8)[0],
                "arg1": struct.unpack_from("<I", buf, off + 12)[0],
                "arg2": struct.unpack_from("<I", buf, off + 16)[0],
                "arg3": struct.unpack_from("<I", buf, off + 20)[0],
            })

        # Palette-Daten (für indexed-Felder, in Feldreihenfolge)
        self.palette: Dict[int, List[int]] = {}
        ptr = info_offset + self.field_storage_info_size
        for i, fi in enumerate(self.field_info):
            if fi["storage_type"] in (STORAGE_BITPACKED_INDEXED, STORAGE_BITPACKED_INDEXED_ARRAY):
                n = fi["additional_data_size"] // 4
                self.palette[i] = list(struct.unpack_from(f"<{n}I", buf, ptr))
                ptr += fi["additional_data_size"]

        # Common-Data-Maps (für commonData-Felder)
        self.common_data: Dict[int, Dict[int, int]] = {}
        for i, fi in enumerate(self.field_info):
            if fi["storage_type"] == STORAGE_COMMON_DATA:
                n = fi["additional_data_size"] // 8
                m = {}
                for j in range(n):
                    off = ptr + j * 8
                    m[struct.unpack_from("<I", buf, off)[0]] = struct.unpack_from("<I", buf, off + 4)[0]
                self.common_data[i] = m
                ptr += fi["additional_data_size"]

        # String-Tabelle über alle Sektionen aufbauen (delta-basiert)
        self.string_table: Dict[int, str] = {}
        self.id_lists: List[List[int]] = []
        self._total_record_data_size = 0
        for s in self.sections:
            if self.is_normal:
                self._total_record_data_size += self.record_size * s["record_count"]
            else:
                self._total_record_data_size += s["offset_records_end"] - s["file_offset"]
        delta = 0
        for s in self.sections:
            if not self.is_normal:
                self.id_lists.append([])
                continue
            st_start = s["file_offset"] + self.record_size * s["record_count"]
            st_end = st_start + s["string_table_size"]
            start = st_start
            p = st_start
            while p < st_end:
                if buf[p] == 0:
                    if p - start > 0:
                        self.string_table[start - st_start + delta] = buf[start:p].decode("utf-8", errors="replace")
                    start = p + 1
                p += 1
            # ID-Liste nach der String-Tabelle
            ids = []
            for j in range(s["id_list_size"] // 4):
                ids.append(struct.unpack_from("<I", buf, st_end + j * 4)[0])
            self.id_lists.append(ids)
            delta += s["string_table_size"]

    # ---- Bit-Reader ----
    @staticmethod
    def _read_bits(buf: bytes, offset_bits: int, size_bits: int, signed: bool = False) -> int:
        if size_bits == 0:
            return 0
        offset_bytes = offset_bits >> 3
        bit_offset = offset_bits & 0x7
        size_bytes = (size_bits + bit_offset + 7) >> 3
        value = 0
        for i in range(size_bytes - 1, -1, -1):
            value = (value << 8) | buf[offset_bytes + i]
        value >>= bit_offset
        value &= (1 << size_bits) - 1
        if signed and (value >> (size_bits - 1)) & 1:
            value -= 1 << size_bits
        return value

    # ---- Records ----
    def get_record_bytes(self, idx: int) -> Optional[bytes]:
        """Record #idx über die erste Sektion (normale Tabellen)."""
        if not self.is_normal or not self.sections:
            return None
        s = self.sections[0]
        if idx >= s["record_count"]:
            return None
        off = s["file_offset"] + idx * self.record_size
        return self.buf[off:off + self.record_size]

    def get_row(self, idx: int) -> Tuple[int, List[int]]:
        """Liefert (record_id, [feldwerte]). String-Felder bleiben Offsets."""
        rec = self.get_record_bytes(idx)
        assert rec is not None
        values: List[int] = []
        record_id = 0
        for fi, info in enumerate(self.field_info):
            st = info["storage_type"]
            if st == STORAGE_NONE:
                v = self._read_bits(rec, info["offset_bits"], info["size_bits"])
            elif st in (STORAGE_BITPACKED, STORAGE_BITPACKED_SIGNED):
                v = self._read_bits(rec, info["offset_bits"], info["size_bits"], signed=(st == STORAGE_BITPACKED_SIGNED))
            elif st == STORAGE_BITPACKED_INDEXED:
                raw = self._read_bits(rec, info["offset_bits"], info["size_bits"])
                v = self.palette.get(fi, [0])[raw] if raw < len(self.palette.get(fi, [])) else 0
            elif st == STORAGE_BITPACKED_INDEXED_ARRAY:
                raw = self._read_bits(rec, info["offset_bits"], info["size_bits"])
                v = raw  # Arrays bleiben Roh-Index (Details je Tabelle)
            elif st == STORAGE_COMMON_DATA:
                v = self.common_data.get(fi, {}).get(record_id, 0)
            else:
                v = 0
            if fi == self.id_index:
                record_id = v
            values.append(v)
        return record_id, values

    def resolve_string(self, field_idx: int, value: int, record_idx: int = 0) -> str:
        """String-Auflösung für 'none'-Felder (Offsets relativ zum Record-Block)."""
        if value == 0:
            return ""
        info = self.field_info[field_idx]
        field_offset_bytes = info["offset_bits"] >> 3
        rel = record_idx * self.record_size + field_offset_bytes + value - self._total_record_data_size
        return self.string_table.get(rel, "")

    def resolve_common_string(self, field_idx: int, value: int) -> str:
        """Common-Data-Werte sind absolute String-Offsets im Record-Block."""
        if value == 0:
            return ""
        return self.string_table.get(value, "")


def read_db2(casc_client, name: str) -> WDC5Reader:
    return WDC5Reader(casc_client.get_file(name))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline.casc_reader import CASCClient, auto_discover_wow_dir

    wow = auto_discover_wow_dir()
    if wow is None:
        print("WoW-Installation nicht gefunden")
        sys.exit(1)
    client = CASCClient(wow)
    client.init()
    name = sys.argv[1] if len(sys.argv) > 1 else "dbfilesclient/broadcasttext.db2"
    r = read_db2(client, name)
    print(f"{name}: {r.record_count} Records, {r.field_count} Felder, RecordSize {r.record_size}")
    print("Storage-Typen:", [(i, fi["storage_type"], fi["offset_bits"], fi["size_bits"]) for i, fi in enumerate(r.field_info)])
    print("String-Tabellen-Einträge:", len(r.string_table))
    for i, s in list(r.string_table.items())[:10]:
        print(f"  [{i}] {s[:80]!r}")
