#!/usr/bin/env python3
"""
Lokaler CASC-Reader für World of Warcraft (pipeline/casc_reader.py)
--------------------------------------------------------------------
Liest Dateien (DB2-Tabellen etc.) direkt aus der lokalen WoW-Installation
(Data/config, Data/indices, Data/data) — ohne CDN, ohne Scraping, ohne
externe Server. Alle deutschen Originaltexte liegen damit lokal vor.

Referenz: LiangYuxuan/wow-casc-dbc (MIT) — hier als Python-Port.
"""

import hashlib
import lzma
import struct
import urllib.request
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LISTFILE_URL = "https://github.com/wowdev/wow-listfile/releases/latest/download/community-listfile.csv"
TACTKEYS_URL = "https://raw.githubusercontent.com/wowdev/TACTKeys/master/WoW.txt"

# ---------------------------------------------------------------------------
# Salsa20 (für verschlüsselte BLTE-Blöcke; Schlüssel kommen aus der KeyRing)
# ---------------------------------------------------------------------------

_SIGMA_32 = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574]
_SIGMA_16 = [0x61707865, 0x3120646E, 0x79622D36, 0x6B206574]


def salsa20_xor(data: bytes, key: bytes, nonce8: bytes) -> bytes:
    """Standard-Salsa20 (20 Runden) — Blizzard-CASC-Variante."""
    if len(key) == 32:
        k = list(struct.unpack("<8I", key))
        sigma = _SIGMA_32
    elif len(key) == 16:
        k = list(struct.unpack("<4I", key)) * 2
        sigma = _SIGMA_16
    else:
        raise ValueError("Salsa20-Schlüssel muss 16 oder 32 Bytes sein")
    n = list(struct.unpack("<2I", nonce8))
    counter = 0
    out = bytearray(len(data))

    def qr(a, b, c, d, st):
        t = (st[a] + st[d]) & 0xFFFFFFFF
        st[b] ^= ((t << 7) | (t >> 25)) & 0xFFFFFFFF
        t = (st[b] + st[a]) & 0xFFFFFFFF
        st[c] ^= ((t << 9) | (t >> 23)) & 0xFFFFFFFF
        t = (st[c] + st[b]) & 0xFFFFFFFF
        st[d] ^= ((t << 13) | (t >> 19)) & 0xFFFFFFFF
        t = (st[d] + st[c]) & 0xFFFFFFFF
        st[a] ^= ((t << 18) | (t >> 14)) & 0xFFFFFFFF

    for block_start in range(0, len(data), 64):
        init = [sigma[0], k[0], k[1], k[2], k[3], sigma[1], n[0], n[1],
                counter, 0, sigma[2], k[4], k[5], k[6], k[7], sigma[3]]
        st = list(init)
        for _ in range(10):
            # ungerade Runde (Spalten)
            qr(0, 4, 8, 12, st)
            qr(5, 9, 13, 1, st)
            qr(10, 14, 2, 6, st)
            qr(15, 3, 7, 11, st)
            # gerade Runde (Zeilen)
            qr(0, 1, 2, 3, st)
            qr(5, 6, 7, 4, st)
            qr(10, 11, 8, 9, st)
            qr(15, 12, 13, 14, st)
        keystream = struct.pack("<16I", *[((init[i] + st[i]) & 0xFFFFFFFF) for i in range(16)])
        chunk = data[block_start:block_start + 64]
        for i in range(len(chunk)):
            out[block_start + i] = chunk[i] ^ keystream[i]
        counter += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# BLTE
# ---------------------------------------------------------------------------

def decode_blte(blte: bytes, ekey_hex: str, keys: Dict[str, bytes],
                allow_missing_keys: bool = False) -> Tuple[bytes, List[str]]:
    """Dekodiert einen BLTE-Container. keys: name(hex) -> Schlüssel.

    allow_missing_keys=True: fehlende Schlüssel werden als Null-Blöcke
    eingefügt (partielle Entschlüsselung für DB2-Dateien, wie im Client).
    Returns (data, missing_key_names)."""
    assert blte[:4] == b"BLTE", "Kein BLTE-Magic"
    header_size = struct.unpack(">I", blte[4:8])[0]
    if header_size == 0:
        # unkomprimiert (ein Block)
        assert hashlib.md5(blte).hexdigest() == ekey_hex
        return blte[8:], []
    assert hashlib.md5(blte[:header_size]).hexdigest() == ekey_hex
    num_blocks = int.from_bytes(blte[9:12], "big")
    out = bytearray()
    missing: List[str] = []
    pos = header_size
    for idx in range(num_blocks):
        csize, dsize = struct.unpack_from(">II", blte, 12 + idx * 24)
        chunk = blte[pos:pos + csize]
        pos += csize
        assert len(chunk) == csize
        flag = chunk[0]
        if flag == 0x4E:  # 'N' none
            dec = chunk[1:]
        elif flag == 0x5A:  # 'Z' zlib
            dec = zlib.decompress(chunk[1:])
        elif flag == 0x46:  # 'F' recursive
            raise NotImplementedError("BLTE Frame(recursive) nicht unterstützt")
        elif flag == 0x45:  # 'E' encrypted
            off = 1
            knl = chunk[off]; off += 1
            name_bytes = chunk[off:off + knl]
            off += knl
            ivl = chunk[off]; off += 1
            iv_buf = chunk[off:off + ivl]; off += ivl
            assert chunk[off] == 0x53  # Salsa20
            off += 1
            key = keys.get(name_bytes[::-1].hex()) or keys.get(name_bytes.hex())
            if key is None:
                if allow_missing_keys:
                    missing.append(name_bytes[::-1].hex())
                    dec = bytes(dsize)
                else:
                    raise KeyError(f"TACT-Key fehlt: {name_bytes[::-1].hex()}")
            else:
                iv = bytearray(8)
                for i in range(8):
                    iv[i] = (iv_buf[i] if i < ivl else 0) ^ ((idx >> (8 * i)) & 0xFF)
                inner = salsa20_xor(chunk[off:], key, bytes(iv))
                # Rekursion: entschlüsselter Block kann selbst 'N'/'Z' sein
                if inner[0] == 0x4E:
                    dec = inner[1:]
                elif inner[0] == 0x5A:
                    dec = zlib.decompress(inner[1:])
                else:
                    raise ValueError(f"Unbekannter innerer Block-Typ nach Entschlüsselung: {inner[0]:#x}")
        else:
            raise ValueError(f"Unbekannter BLTE-Block-Typ: {flag:#x}")
        if len(dec) != dsize:
            raise ValueError(f"Größen-Mismatch: {len(dec)} != {dsize}")
        out += dec
    return bytes(out), missing


# ---------------------------------------------------------------------------
# Lokale Journal-Indizes (Data/data/*.idx) — portiert aus wow.export
# ---------------------------------------------------------------------------

def parse_journal_index(buffer: bytes) -> Dict[str, Tuple[int, int, int]]:
    """Liefert {ekey_prefix(9 Bytes, hex): (archive_nr, offset, size)}."""
    pos = 0
    header_hash_size = struct.unpack_from("<i", buffer, pos)[0]
    pos += 4
    pos += 4                      # headerHash uint32
    pos += header_hash_size       # headerHash byte[]
    pos = (pos + 0x0F) & ~0x0F    # nächste 0x10-Grenze
    data_length = struct.unpack_from("<i", buffer, pos)[0]
    pos += 4
    pos += 4
    entries: Dict[str, Tuple[int, int, int]] = {}
    for _ in range(data_length // 18):
        if pos + 18 > len(buffer):
            break
        key = buffer[pos:pos + 9].hex()
        pos += 9
        idx_high = buffer[pos]
        pos += 1
        idx_low = struct.unpack_from(">i", buffer, pos)[0]
        pos += 4
        size = struct.unpack_from("<i", buffer, pos)[0]
        pos += 4
        archive = (idx_high << 2) | ((idx_low & 0xC0000000) >> 30)
        offset = idx_low & 0x3FFFFFFF
        entries[key] = (archive, offset, size)
    return entries


# ---------------------------------------------------------------------------
# Split-Index (.index / .idx) — portiert aus archiveIndex.ts
# ---------------------------------------------------------------------------

def parse_split_index(buffer: bytes, ckey_hex: str) -> Dict[str, Tuple[int, int]]:
    """Liefert {ekey_hex: (size, offset)} eines Split-Index-Files."""
    size = len(buffer)
    checksum_size = None
    for cs in range(10, -1, -1):
        vo = size - cs - 12
        if vo >= 0 and buffer[vo] == 1:
            checksum_size = cs
            break
    assert checksum_size is not None, "Split-Index-Footer nicht gefunden"

    version_offset = size - checksum_size - 12
    footer_offset = version_offset - checksum_size

    block_size_kb = buffer[version_offset + 3]
    offset_bytes = buffer[version_offset + 4]
    size_bytes = buffer[version_offset + 5]
    key_size = buffer[version_offset + 6]
    num_elements = struct.unpack_from("<I", buffer, version_offset + 8)[0]

    entry_size = key_size + offset_bytes + size_bytes
    block_size = block_size_kb * 1024
    num_blocks = footer_offset // (block_size + key_size + checksum_size)
    toc_size = (key_size + checksum_size) * num_blocks
    toc = buffer[footer_offset - toc_size:footer_offset]

    result: Dict[str, Tuple[int, int]] = {}
    for i in range(num_blocks):
        last_ekey = toc[i * key_size:(i + 1) * key_size].hex()
        block = buffer[i * block_size:(i + 1) * block_size]
        length = 0
        while length < block_size:
            eo = length * entry_size
            ekey = block[eo:eo + key_size].hex()
            fsize = int.from_bytes(block[eo + key_size:eo + key_size + size_bytes], "big")
            foffset = int.from_bytes(block[eo + key_size + size_bytes:eo + entry_size], "big")
            result[ekey] = (fsize, foffset)
            length += 1
            if ekey == last_ekey:
                break
    return result


# ---------------------------------------------------------------------------
# TACT-Dateien (root / encoding) im Klartext nach BLTE
# ---------------------------------------------------------------------------

def parse_build_config(text: str) -> Dict[str, str]:
    cfg = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def jenkins96_hash(name: str) -> str:
    """Name-Hash des TACT-Root (hashlittle2, Pfad mit Backslashes, GROSS).

    Achtung: nur ASCII-Buchstaben werden vergrößert — str.upper() würde
    Nicht-ASCII-Zeichen verfälschen (z. B. 'ß' -> 'SS')."""
    key = name.replace("/", "\\")
    key = "".join(ch.upper() if "a" <= ch <= "z" else ch for ch in key)
    length = len(key)
    offset = 0
    a = b = c = (0xDEADBEEF + length) & 0xFFFFFFFF

    def to_i32(v: int) -> int:
        v &= 0xFFFFFFFF
        return v - 0x100000000 if v >= 0x80000000 else v

    def rol(v: int, n: int) -> int:
        return ((v << n) | ((v & 0xFFFFFFFF) >> (32 - n))) & 0xFFFFFFFF

    def mix():
        nonlocal a, b, c
        a = to_i32(a - c); a = to_i32(a ^ rol(c, 4)); c = to_i32(c + b)
        b = to_i32(b - a); b = to_i32(b ^ rol(a, 6)); a = to_i32(a + c)
        c = to_i32(c - b); c = to_i32(c ^ rol(b, 8)); b = to_i32(b + a)
        a = to_i32(a - c); a = to_i32(a ^ rol(c, 16)); c = to_i32(c + b)
        b = to_i32(b - a); b = to_i32(b ^ rol(a, 19)); a = to_i32(a + c)
        c = to_i32(c - b); c = to_i32(c ^ rol(b, 4)); b = to_i32(b + a)

    while length - offset > 12:
        a = to_i32(a + sum(ord(key[offset + i]) << (8 * i) for i in range(4)))
        b = to_i32(b + sum(ord(key[offset + 4 + i]) << (8 * i) for i in range(4)))
        c = to_i32(c + sum(ord(key[offset + 8 + i]) << (8 * i) for i in range(4)))
        mix()
        offset += 12

    remaining = length - offset
    if remaining > 0:
        if remaining >= 12:
            c = to_i32(c + (ord(key[offset + 11]) << 24))
        if remaining >= 11:
            c = to_i32(c + (ord(key[offset + 10]) << 16))
        if remaining >= 10:
            c = to_i32(c + (ord(key[offset + 9]) << 8))
        if remaining >= 9:
            c = to_i32(c + ord(key[offset + 8]))
        if remaining >= 8:
            b = to_i32(b + (ord(key[offset + 7]) << 24))
        if remaining >= 7:
            b = to_i32(b + (ord(key[offset + 6]) << 16))
        if remaining >= 6:
            b = to_i32(b + (ord(key[offset + 5]) << 8))
        if remaining >= 5:
            b = to_i32(b + ord(key[offset + 4]))
        if remaining >= 4:
            a = to_i32(a + (ord(key[offset + 3]) << 24))
        if remaining >= 3:
            a = to_i32(a + (ord(key[offset + 2]) << 16))
        if remaining >= 2:
            a = to_i32(a + (ord(key[offset + 1]) << 8))
        if remaining >= 1:
            a = to_i32(a + ord(key[offset + 0]))

        c = to_i32(c ^ b); c = to_i32(c - rol(b, 14))
        a = to_i32(a ^ c); a = to_i32(a - rol(c, 11))
        b = to_i32(b ^ a); b = to_i32(b - rol(a, 25))
        c = to_i32(c ^ b); c = to_i32(c - rol(b, 16))
        a = to_i32(a ^ c); a = to_i32(a - rol(c, 4))
        b = to_i32(b ^ a); b = to_i32(b - rol(a, 14))
        c = to_i32(c ^ b); c = to_i32(c - rol(b, 24))

    return f"{b & 0xFFFFFFFF:08x}{c & 0xFFFFFFFF:08x}"


def parse_root_file(buf: bytes) -> Tuple[Dict[str, int], Dict[int, List[Dict]]]:
    """Returns (namehash_jenkins96 -> filedataid, filedataid -> [{ckey, locale_flags}])."""
    name2fid: Dict[str, int] = {}
    fid2ckey: Dict[int, List[Dict]] = {}
    magic = struct.unpack_from("<I", buf, 0)[0]
    assert magic == 0x4D465354, f"Root-Magic falsch: {magic:#x}"
    first_entry = struct.unpack_from("<I", buf, 4)[0]
    new_format = first_entry < 100
    if new_format:
        version = struct.unpack_from("<I", buf, 8)[0]
        total_count = struct.unpack_from("<I", buf, 12)[0]
        named_count = struct.unpack_from("<I", buf, 16)[0]
        header_size = first_entry
    else:
        version = 0
        total_count = first_entry
        named_count = struct.unpack_from("<I", buf, 8)[0]
        header_size = 12

    allow_non_named = total_count != named_count
    pointer = header_size
    while pointer < len(buf):
        num_records = struct.unpack_from("<I", buf, pointer)[0]
        if num_records == 0:
            break
        if version >= 2:
            locale_flags = struct.unpack_from("<I", buf, pointer + 4)[0]
            content_flags = (struct.unpack_from("<I", buf, pointer + 8)[0]
                             | struct.unpack_from("<I", buf, pointer + 12)[0]
                             | (buf[pointer + 16] << 17))
            pointer += 17
        else:
            content_flags = struct.unpack_from("<I", buf, pointer + 4)[0]
            locale_flags = struct.unpack_from("<I", buf, pointer + 8)[0]
            pointer += 12

        fids = []
        cur = -1
        for _ in range(num_records):
            cur += struct.unpack_from("<I", buf, pointer)[0] + 1
            fids.append(cur)
            pointer += 4
        for fid in fids:
            ckey = buf[pointer:pointer + 16].hex()
            pointer += 16
            fid2ckey.setdefault(fid, []).append({
                "ckey": ckey,
                "locale_flags": locale_flags,
            })
        if not (allow_non_named and (content_flags & 0x10000000)):  # NoNameHash
            for fid in fids:
                name_hash = buf[pointer:pointer + 8][::-1].hex()  # UInt64LE
                pointer += 8
                name2fid[name_hash] = fid
    return name2fid, fid2ckey


# ---------------------------------------------------------------------------
# CASC-Client (lokale Installation)
# ---------------------------------------------------------------------------

class CASCClient:
    def __init__(self, wow_dir: Path):
        self.wow_dir = Path(wow_dir)
        self.data_dir = self.wow_dir / "Data"
        self.keys: Dict[str, bytes] = {}
        self.archives: List[Path] = []
        self.index_files: List[Path] = []
        self.root_names: Dict[str, int] = {}
        self.root_fids: Dict[int, List[Dict]] = {}
        self.encoding_ckey2ekey: Dict[str, str] = {}
        self._archive_size = 0
        self._journal: Optional[Dict[str, Tuple[int, int, int]]] = None
        self._listfile: Optional[Dict[str, int]] = None
        self._tact_keys: Optional[Dict[str, bytes]] = None

    # ---- Aufbau ----
    def init(self) -> None:
        build_info = self._read_build_info()
        # Config-Dateien: alle 4 lesen und nach Inhalt identifizieren
        config_dir = self.data_dir / "config"
        build_cfg_text, cdn_cfg_text, keyring_text = None, None, None
        for f in config_dir.rglob("*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8", errors="ignore")
                if text.startswith("# Build Configuration") or "\nroot = " in text:
                    build_cfg_text = text
                elif "archive-group" in text:
                    cdn_cfg_text = text
                elif text.startswith("key-"):
                    keyring_text = text
        assert build_cfg_text and cdn_cfg_text, "Build-/CDN-Config nicht gefunden"

        # KeyRing: TACT-Schlüssel lokal!
        for line in keyring_text.splitlines() if keyring_text else []:
            line = line.strip()
            if line.startswith("key-"):
                k, v = line.split(" = ")
                name = k[4:]
                self.keys[name] = bytes.fromhex(v)

        # Öffentliche TACT-Key-Liste ergänzen (einmalig gecacht, community-gepflegt)
        try:
            for lookup, key in self._ensure_tact_keys().items():
                self.keys.setdefault(lookup, key)
        except Exception as e:
            print(f"  Hinweis: TACT-Keys nicht ladbar ({e}) — verschlüsselte Dateien bleiben teilweise unlesbar")

        build_cfg = parse_build_config(build_cfg_text)
        cdn_cfg = parse_build_config(cdn_cfg_text)

        # Archive + Indizes
        archive_keys = cdn_cfg.get("archives", "").split()
        index_dir = self.data_dir / "indices"
        self.index_files = [index_dir / f"{k}.index" for k in archive_keys if (index_dir / f"{k}.index").exists()]
        self.index_files.sort(key=lambda p: p.name)
        for i in range(200):
            cand = self.data_dir / "data" / f"data.{i:03d}"
            if cand.exists():
                self.archives.append(cand)
            else:
                break
        if self.archives:
            self._archive_size = self.archives[0].stat().st_size

        # Encoding-Tabelle lesen (CKey/EKey aus Build-Config)
        enc_c, enc_e = build_cfg["encoding"].split()[:2]
        enc_buf = self.read_by_ekey(enc_e, enc_c)
        self._parse_encoding(enc_buf)

        # Root-Datei
        root_c = build_cfg["root"].split()[0]
        root_e = self.encoding_ckey2ekey.get(root_c) or build_cfg["root"].split()[-1]
        root_buf = self.read_by_ekey(root_e, root_c)
        names, fids = parse_root_file(root_buf)
        self.root_names = names
        self.root_fids = fids

    def _read_build_info(self) -> Dict[str, str]:
        bi = self.wow_dir / ".build.info"
        lines = bi.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("|")
        data = lines[1].split("|") if len(lines) > 1 else []
        return {header[i].split("!")[0]: data[i] for i in range(min(len(header), len(data)))}

    def _parse_encoding(self, buf: bytes) -> None:
        magic = struct.unpack_from(">H", buf, 0)[0]
        assert magic == 0x454E, f"Encoding-Magic falsch: {magic:#x}"
        hash_ckey = buf[3]
        hash_ekey = buf[4]
        ckey_page_kb = struct.unpack_from(">H", buf, 5)[0]
        ckey_page_count = struct.unpack_from(">I", buf, 9)[0]
        spec_size = struct.unpack_from(">I", buf, 18)[0]
        spec_offset = 22

        ckey_page_index_offset = spec_offset + spec_size
        entry_size = hash_ckey + 0x10
        ckey_page_offset = ckey_page_index_offset + entry_size * ckey_page_count
        ckey_page_size = ckey_page_kb * 1024
        for i in range(ckey_page_count):
            page = buf[ckey_page_offset + i * ckey_page_size:
                      ckey_page_offset + (i + 1) * ckey_page_size]
            ptr = 0
            while ptr < ckey_page_size:
                count = page[ptr]
                ptr += 1
                if count == 0:
                    break
                ptr += 5  # fileSize
                ckey = page[ptr:ptr + hash_ckey].hex()
                ptr += hash_ckey
                if count == 1:
                    ekey = page[ptr:ptr + hash_ekey].hex()
                    ptr += hash_ekey
                    self.encoding_ckey2ekey[ckey] = ekey
                else:
                    ekeys = []
                    for _ in range(count):
                        ekeys.append(page[ptr:ptr + hash_ekey].hex())
                        ptr += hash_ekey
                    self.encoding_ckey2ekey[ckey] = ekeys[0]

    # ---- Lesezugriff ----
    def read_by_ekey(self, ekey_hex: str, expect_ckey: str = None) -> bytes:
        if not self._journal:
            self._load_journal()
        key9 = ekey_hex[:18]
        entry = self._journal.get(key9)
        if entry is None:
            raise FileNotFoundError(f"EKey nicht lokal indiziert: {ekey_hex[:16]}…")
        archive_nr, offset, size = entry
        arch = self.data_dir / "data" / f"data.{archive_nr:03d}"
        if not arch.exists():
            raise FileNotFoundError(f"Archiv {archive_nr} fehlt lokal für {ekey_hex[:16]}…")
        with open(arch, "rb") as f:
            f.seek(offset)
            raw = f.read(size)
        # BLTE beginnt je nach Archiv-Gruppe direkt am Offset oder nach einem
        # 0x1E-Bytes-Datei-Header — beides empirisch prüfen.
        blte = None
        if raw[:4] == b"BLTE":
            blte = raw
        elif len(raw) > 0x1E + 4 and raw[0x1E:0x1E + 4] == b"BLTE":
            blte = raw[0x1E:]
        if blte is None:
            raise ValueError(f"Kein BLTE-Magic bei {ekey_hex[:16]}… (Offset {offset}, Größe {size})")
        buf, missing = decode_blte(blte, ekey_hex, self.keys, allow_missing_keys=True)
        if missing:
            print(f"  Hinweis: {len(missing)} verschlüsselte Blöcke ohne Key (Null-Füllung): {missing[0]}…")
        if expect_ckey and not missing and hashlib.md5(buf).hexdigest() != expect_ckey:
            raise ValueError(f"CKey-Mismatch für {ekey_hex[:16]}…")
        return buf

    def _load_journal(self) -> None:
        self._journal = {}
        data_dir = self.data_dir / "data"
        for f in data_dir.glob("*.idx"):
            self._journal.update(parse_journal_index(f.read_bytes()))
        if not self._journal:
            raise FileNotFoundError("Keine lokalen Journal-Indizes (Data/data/*.idx) gefunden")

    def _lookup_ekey(self, ekey_hex: str) -> Tuple[int, int]:
        if not self._journal:
            self._load_journal()
        entry = self._journal.get(ekey_hex[:18])
        if entry is None:
            raise FileNotFoundError(f"EKey nicht lokal indiziert: {ekey_hex[:16]}…")
        return entry[1], entry[2]

    # ---- Name -> Inhalt ----
    def _ensure_tact_keys(self) -> Dict[str, bytes]:
        """Öffentliche TACT-Schlüssel (wowdev/TACTKeys), einmalig gecacht."""
        if not self._tact_keys:
            cache = Path.home() / ".cache" / "echoes-of-azeroth" / "tactkeys.txt"
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                print(f"  Lade öffentliche TACT-Keys (einmalig): {cache}")
                urllib.request.urlretrieve(TACTKEYS_URL, cache)
            m = {}
            for line in cache.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and len(parts[0]) == 16 and len(parts[1]) == 32:
                    try:
                        m[parts[0].lower()] = bytes.fromhex(parts[1])
                    except ValueError:
                        pass
            self._tact_keys = m
        return self._tact_keys

    def _ensure_listfile(self) -> Dict[str, int]:
        """Community-Listfile (name -> FileDataID), einmalig gecacht."""
        if not self._listfile:
            cache = self.wow_dir.parent / "wow-listfile.csv"
            if not cache.exists():
                console_cache = Path.home() / ".cache" / "echoes-of-azeroth" / "wow-listfile.csv"
                cache = console_cache
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                print(f"  Lade Community-Listfile (einmalig, ~30 MB): {cache}")
                urllib.request.urlretrieve(LISTFILE_URL, cache)
            m = {}
            with open(cache, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(";")
                    if len(parts) == 2:
                        fid, name = parts
                        if fid.strip().isdigit():
                            m[name.strip().lower()] = int(fid.strip())
            self._listfile = m
        return self._listfile

    def get_file(self, name: str, locale_flags: int = 0x20) -> bytes:
        """Liest eine Datei. Bevorzugt die lokal vorhandene deDE-Variante
        (moderne Builds splitten DB2-Dateien pro Sprache)."""
        # Weg 1: Name-Hash direkt aus dem Root (jenkins96)
        name_hash = jenkins96_hash(name)
        fid = self.root_names.get(name_hash)
        # Weg 2: Community-Listfile -> FileDataID
        if fid is None:
            fid = self._ensure_listfile().get(name.lower())
        if fid is None:
            raise FileNotFoundError(f"Datei nicht im Root/Listfile: {name}")
        candidates = self.root_fids.get(fid, [])
        if not candidates:
            raise FileNotFoundError(f"Kein CKey für {name}")

        def local_of(cand) -> bool:
            ek = self.encoding_ckey2ekey.get(cand["ckey"])
            return ek is not None and ek[:18] in self._journal

        # Priorität: deDE + lokal > lokal > deDE > erster Kandidat
        chosen = None
        for cand in candidates:
            if (cand["locale_flags"] & locale_flags) and local_of(cand):
                chosen = cand
                break
        if chosen is None:
            for cand in candidates:
                if local_of(cand):
                    chosen = cand
                    break
        if chosen is None:
            for cand in candidates:
                if cand["locale_flags"] & locale_flags:
                    chosen = cand
                    break
        if chosen is None:
            chosen = candidates[0]
        ckey = chosen["ckey"]
        ekey = self.encoding_ckey2ekey.get(ckey)
        if ekey is None:
            raise FileNotFoundError(f"Kein EKey für {name} ({ckey[:16]}…)")
        return self.read_by_ekey(ekey, ckey)


def auto_discover_wow_dir() -> Optional[Path]:
    """Findet die WoW-Retail-Installation (Steam/Proton, Wine, Standard)."""
    candidates = [
        Path.home() / ".local/share/Steam/steamapps/compatdata",
    ]
    for base in candidates:
        if not base.exists():
            continue
        for prefix in base.iterdir():
            wow = prefix / "pfx/drive_c/Program Files (x86)/World of Warcraft"
            if (wow / ".build.info").exists():
                return wow
    return None


if __name__ == "__main__":
    import sys
    wow = auto_discover_wow_dir()
    if wow is None:
        print("WoW-Installation nicht gefunden — WOW_DIR als Argument übergeben")
        sys.exit(1)
    print("WoW:", wow)
    client = CASCClient(wow)
    client.init()
    print("Archive:", len(client.archives), "| Indizes:", len(client.index_files), "| TACT-Keys:", len(client.keys))
    print("Encoding-Einträge:", len(client.encoding_ckey2ekey))
    print("Root-Einträge (FIDs):", len(client.root_fids))
    for name in sys.argv[1:]:
        try:
            buf = client.get_file(name)
            print(f"{name}: {len(buf):,} Bytes | Magic: {buf[:4]!r}")
        except Exception as e:
            print(f"{name}: FEHLER — {e}")
