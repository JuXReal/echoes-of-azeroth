#!/usr/bin/env python3
"""
Step 6: Audio-Postprocessing & Addon-Export (06_audio_fx.py)
------------------------------------------------------------
1. Rassenspezifische DSP-Ketten via FFmpeg (`af_chain` aus config.yaml):
   - Blood Elf: Präsenz-Boost + Hall
   - Void Elf: Dual-Chorus + dunkler Hall
   - Entartung: Pitch −4 % + Echo
   - Troll: Bass-Boost + Echo
   - Undead: Hochpass + EQ-Boost + Delay
   - Tauren / Gnome / Goblin: Pitch-/EQ-Profile
2. Lautheits-Normalisierung nach EBU R128 (loudnorm=I=-16:TP=-1.5:LRA=11).
3. Export als OGG Vorbis (libvorbis, -q:a 4, 44,1 kHz) mit den exakten
   ChattyLittleNpc-Dateinamen (<QuestID>_<Phase>.ogg) nach output/final_ogg/.
4. Baut das fertige Addon-Paket (ChattyLittleNpc_<Expansion>_deDE_voiceovers
   mit .toc, Main.lua, VoiceoversList.lua inkl. OggVorbis-Dauern) und
   installiert es optional direkt in WoW _retail_/Interface/AddOns/.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
import yaml
from mutagen.oggvorbis import OggVorbis
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.live_state import begin_step, finish_step, increment, update_current

console = Console()


def compute_match_eq_gains(
    ref_path: Path,
    tts_path: Path,
    bands: List[float],
    max_boost_db: float = 8.0,
    max_cut_db: float = -6.0,
    min_gain_db: float = 0.5,
) -> List[Tuple[float, float]]:
    """
    Spektrales EQ-Matching: vergleicht das gemittelte Spektrum des englischen
    Originals (Referenz) mit dem des deutschen Takes und liefert pro Band eine
    Korrektur in dB (Lautstärke-normalisiert, geglättet, begrenzt).
    """
    try:
        ref, sr_ref = sf.read(str(ref_path), always_2d=True)
        tts, sr_tts = sf.read(str(tts_path), always_2d=True)
    except Exception:
        return []
    ref = np.mean(ref, axis=1).astype(np.float32)
    tts = np.mean(tts, axis=1).astype(np.float32)
    if len(ref) < sr_ref or len(tts) < sr_tts:
        return []

    def band_power_db(x, sr, f0, f1):
        n = len(x)
        win = np.hanning(n).astype(np.float32)
        X = np.fft.rfft(x * win)
        freqs = np.fft.rfftfreq(n, 1.0 / sr)
        mask = (freqs >= f0) & (freqs < f1)
        if not mask.any():
            return None
        p = float(np.mean(np.abs(X[mask]) ** 2))
        return 10.0 * np.log10(max(p, 1e-12))

    ref_total = 10.0 * np.log10(max(float(np.mean(ref ** 2)), 1e-12))
    tts_total = 10.0 * np.log10(max(float(np.mean(tts ** 2)), 1e-12))

    f_max = min(11500.0, float(sr_tts // 2) - 1000.0)
    freqs: List[float] = []
    gains: List[float] = []
    for i, f0 in enumerate(bands):
        f1 = bands[i + 1] if i + 1 < len(bands) else f_max
        if f0 >= f_max:
            continue
        rb = band_power_db(ref, sr_ref, f0, f1)
        tb = band_power_db(tts, sr_tts, f0, f1)
        if rb is None or tb is None:
            continue
        g = (rb - ref_total) - (tb - tts_total)
        g = float(np.clip(g, max_cut_db, max_boost_db))
        freqs.append((f0 + min(f1, f_max)) / 2.0)
        gains.append(g)

    if not gains:
        return []
    # Bänder glätten, um Kammfilter-Artefakte zu vermeiden
    gains = np.convolve(gains, [0.25, 0.5, 0.25], mode="same")
    # Nur relevante Korrekturen behalten (hält die FFmpeg-Kette kurz)
    return [
        (round(float(f)), round(float(g), 2))
        for f, g in zip(freqs, gains)
        if abs(g) >= min_gain_db
    ]


def process_audio_fx_and_export_ogg(
    input_wav: Path,
    output_ogg: Path,
    race_af_chain: str,
    loudnorm_cfg: Dict,
    ogg_cfg: Dict,
    eq_filters: str = "",
) -> float:
    """
    Runs FFmpeg with optional EQ-match filters + race-specific DSP chain +
    EBU R128 loudnorm + libvorbis q:a 4. Returns final OGG duration in seconds.
    """
    output_ogg.parent.mkdir(parents=True, exist_ok=True)

    i_lufs = loudnorm_cfg.get("integrated_lufs", -16.0)
    tp_db = loudnorm_cfg.get("true_peak_db", -1.5)
    lra = loudnorm_cfg.get("lra", 11.0)
    target_sr = ogg_cfg.get("sample_rate", 44100)
    quality = ogg_cfg.get("quality", 4)

    parts = [
        eq_filters,
        race_af_chain,
        f"loudnorm=I={i_lufs}:TP={tp_db}:LRA={lra}",
        "afade=t=in:st=0:d=0.015",
    ]
    full_af = ",".join(p for p in parts if p)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_wav),
        "-af",
        full_af,
        "-ar",
        str(target_sr),
        "-ac",
        "1",
        "-c:a",
        ogg_cfg.get("codec", "libvorbis"),
        "-q:a",
        str(quality),
        str(output_ogg),
    ]
    subprocess.run(cmd, check=True)

    ogg_info = OggVorbis(str(output_ogg))
    return round(ogg_info.info.length, 2)


def generate_wow_de_addon_pack(
    addon_dir: Path,
    final_ogg_dir: Path,
    addon_name: str,
    interface_version: str,
) -> int:
    """
    Builds a complete, native ChattyLittleNpc locale pack (`ChattyLittleNpc_Midnight_deDE_voiceovers`)
    with `.toc`, `Main.lua`, `VoiceoversList.lua`, and `voiceovers/*.ogg`.
    """
    vo_subdir = addon_dir / "voiceovers"
    vo_subdir.mkdir(parents=True, exist_ok=True)

    ogg_files = sorted(final_ogg_dir.glob("*.ogg"))
    voiceovers_list = []
    durations_map = {}

    for ogg_p in ogg_files:
        dest_p = vo_subdir / ogg_p.name
        shutil.copy2(ogg_p, dest_p)
        voiceovers_list.append(ogg_p.name)
        try:
            dur = round(OggVorbis(str(dest_p)).info.length, 2)
        except Exception:
            dur = 5.0
        durations_map[ogg_p.name] = dur

    # 1. Write .toc
    toc_content = (
        f"## Interface: {interface_version}\n"
        f"## Title: Chatty Little NPC: Midnight Voiceovers (deDE)\n"
        f"## Notes: Deutsche KI-Sprachausgabe (XTTS-v2) für World of Warcraft: Midnight\n"
        f"## Author: WoW-Chatty-DE-Pipeline\n"
        f"## Version: 1.0.0\n"
        f"## Dependencies: ChattyLittleNpc\n\n"
        f"Main.lua\n"
        f"VoiceoversList.lua\n"
    )
    (addon_dir / f"{addon_name}.toc").write_text(toc_content, encoding="utf-8")

    # 2. Write Main.lua
    main_lua = (
        f"---@class {addon_name}: table\n"
        f"local {addon_name} = {{}}\n"
        f'_G["{addon_name}"] = {addon_name}\n\n'
        f"{addon_name}.Metadata = {{\n"
        f"    ContainsQuestVoiceovers = true,\n"
        f"    ContainsGossipVoiceovers = false,\n"
        f"    ContainsGameObjectVoiceovers = false,\n"
        f"    ContainsItemVoiceovers = false\n"
        f"}}\n"
    )
    (addon_dir / "Main.lua").write_text(main_lua, encoding="utf-8")

    # 3. Write VoiceoversList.lua
    lines = [
        f"---@class {addon_name}",
        f'local {addon_name} = _G["{addon_name}"]',
        "",
        f"{addon_name}.Voiceovers = {{",
    ]
    for fname in voiceovers_list:
        lines.append(f"    '{fname}',")
    lines.append("}")
    lines.append("")
    lines.append(f"{addon_name}.VoiceoverDurations = {{")
    for fname in voiceovers_list:
        lines.append(f'    ["{fname}"] = {durations_map[fname]},')
    lines.append("}")

    (addon_dir / "VoiceoversList.lua").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(voiceovers_list)


def main():
    parser = argparse.ArgumentParser(description="Step 6: FFmpeg Race-FX, EBU R128 Loudnorm & OGG Addon Export.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--install-to-wow", action="store_true", default=True, help="Copy generated deDE pack to WoW AddOns dir")
    parser.add_argument("--skip-audit", action="store_true", help="Skip the mandatory Step 7 100-quest audit")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    with open(project_root / args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    pilot_path = project_root / cfg["paths"]["data_raw_de_text"] / "midnight_de_pilot_20.json"
    final_ogg_dir = project_root / cfg["paths"]["output_final_ogg"]
    addon_pack_dir = project_root / cfg["paths"]["output_addon_pack"]
    final_ogg_dir.mkdir(parents=True, exist_ok=True)

    fx_cfg = cfg["audio_fx"]
    race_profiles = fx_cfg["race_profiles"]
    loudnorm_cfg = fx_cfg["loudnorm"]
    ogg_cfg = fx_cfg["ogg_export"]
    eq_cfg = fx_cfg.get("eq_matching", {})

    pilot_data = json.loads(pilot_path.read_text(encoding="utf-8"))
    entries = pilot_data["entries"]

    console.rule("[bold cyan]Step 6: FFmpeg Audio Post-Processing (Race-FX + EBU R128 Loudnorm + OGG Vorbis)[/bold cyan]")
    begin_step("fx", total=len(entries))

    table = Table(title="Processed & Mastered German OGG Voiceovers")
    table.add_column("File", style="cyan")
    table.add_column("Speaker", style="green")
    table.add_column("Race Profile", style="magenta")
    table.add_column("DSP Filter Chain", style="dim")
    table.add_column("EN Dur", justify="right")
    table.add_column("DE Dur", justify="right", style="bold green")

    for e in entries:
        raw_wav = Path(e["raw_tts_wav"])
        out_ogg = final_ogg_dir / e["target_ogg_filename"]
        race = e.get("race", "Default")
        profile = race_profiles.get(race, race_profiles["Default"])
        af_chain = profile["af_chain"]

        update_current({
            "entry_id": e["entry_id"],
            "npc_name": e["npc_name"],
            "quest_title_de": e.get("quest_title_de", ""),
            "phase": e.get("phase", ""),
            "status": "mastering",
            "cer": None,
        })

        # Spektrales EQ-Matching gegen das englische Original (behebt "dünnen" Klang)
        eq_filters = ""
        eq_match_info = None
        if eq_cfg.get("enabled", True):
            src_ogg = Path(e.get("source_ogg_path") or "")
            if src_ogg.is_file():
                eq_gains = compute_match_eq_gains(
                    src_ogg,
                    raw_wav,
                    bands=[float(b) for b in eq_cfg.get("bands", [80, 120, 180, 250, 350, 500, 700, 1000, 1400, 2000, 2800, 4000, 5600, 8000, 11000])],
                    max_boost_db=float(eq_cfg.get("max_boost_db", 8.0)),
                    max_cut_db=float(eq_cfg.get("max_cut_db", -6.0)),
                    min_gain_db=float(eq_cfg.get("min_gain_db", 0.5)),
                )
                if eq_gains:
                    eq_filters = ",".join(
                        f"equalizer=f={f}:width_type=q:width=0.6:g={g:.2f}"
                        for f, g in eq_gains
                    )
                    eq_match_info = eq_gains

        final_dur = process_audio_fx_and_export_ogg(
            input_wav=raw_wav,
            output_ogg=out_ogg,
            race_af_chain=af_chain,
            loudnorm_cfg=loudnorm_cfg,
            ogg_cfg=ogg_cfg,
            eq_filters=eq_filters,
        )
        increment(processed=1)

        e["final_ogg_path"] = str(out_ogg)
        e["final_ogg_duration_sec"] = final_dur
        e["applied_race_fx"] = {
            "race": race,
            "description": profile["description"],
            "af_chain": af_chain,
            "loudnorm": f"I={loudnorm_cfg['integrated_lufs']} LUFS, TP={loudnorm_cfg['true_peak_db']} dBTP",
        }
        e["applied_eq_match"] = eq_match_info

        table.add_row(
            e["target_ogg_filename"],
            e["npc_name"],
            race,
            profile["description"][:42] + "...",
            f"{e['source_duration_sec']:.1f}s",
            f"{final_dur:.2f}s",
        )

    console.print(table)
    pilot_path.write_text(json.dumps(pilot_data, indent=2, ensure_ascii=False), encoding="utf-8")
    finish_step(ok=True)

    # Build complete WoW Addon Pack
    addon_name = pilot_data.get("addon_architecture", {}).get("target_pack_name", cfg["project"]["target_addon_name"])
    addon_pack_dir = project_root / "output" / addon_name
    iface_ver = cfg["project"]["interface_version"]
    pack_count = generate_wow_de_addon_pack(addon_pack_dir, final_ogg_dir, addon_name, iface_ver)
    console.print(f"[bold green]✓ Built ready-to-load WoW Addon Pack: {addon_pack_dir} ({pack_count} OGG files)[/bold green]")

    # Also deploy to WoW _retail_/Interface/AddOns/ChattyLittleNpc_<Exp>_deDE_voiceovers
    env_file = project_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    wow_addons_dir = Path(os.getenv("WOW_ADDONS_DIR") or cfg["paths"]["wow_addons_dir"])
    if args.install_to_wow and wow_addons_dir.exists():
        live_target = wow_addons_dir / addon_name
        if live_target.exists():
            shutil.rmtree(live_target)
        shutil.copytree(addon_pack_dir, live_target)
        console.print(f"[bold cyan]✓ Installed live into WoW AddOns folder -> {live_target}[/bold cyan]")

    # Mandatory Quality Assurance Gate: Automatically run Step 7
    if not args.skip_audit:
        audit_script = project_root / "pipeline" / "07_independent_audit_100.py"
        if audit_script.exists():
            console.print("\n[bold yellow]🛡️  Triggering Mandatory Step 7 Quality Audit...[/bold yellow]")
            import subprocess, sys
            py_bin = sys.executable
            subprocess.run([py_bin, str(audit_script), "--sample-size", "100"], check=False)


if __name__ == "__main__":
    main()
