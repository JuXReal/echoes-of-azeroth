#!/usr/bin/env python3
"""
Step 6: Audio Post-Processing & Addon Export (06_audio_fx.py)
-------------------------------------------------------------
1. Applies race-specific acoustic DSP chains via FFmpeg (`af_chain` from config.yaml):
   - Blood Elf: Crisp high-mid presence + subtle Silvermoon hall reflection
   - Void Elf: Ethereal dual-phase void whisper & dark resonance
   - Entartung (Void Wretch): Slight pitch-down & eerie cave shadow echo
   - Troll (Amani): Warm chest resonance + temple ambience
   - Undead: Raspy high-pass + hollow metallic dual-delay
   - Tauren / Gnome / Goblin: Formant-preserving pitch/EQ profiles.
2. Normalizes loudness to EBU R128 (`loudnorm=I=-16:TP=-1.5:LRA=11`) matching
   World of Warcraft's MASTER audio channel level.
3. Exports as OGG Vorbis (`libvorbis`, `-q:a 4`, 44.1 kHz) with exact ChattyLittleNpc
   filenames (`<QuestID>_<Phase>.ogg`) into `output/final_ogg/`.
4. Builds a complete, ready-to-play WoW Addon pack:
   `ChattyLittleNpc_Midnight_deDE_voiceovers` (including `.toc`, `Main.lua`,
   and `VoiceoversList.lua` with exact `OggVorbis` durations) and optionally
   installs/symlinks it directly into the live WoW `_retail_/Interface/AddOns/` folder!
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import yaml
from mutagen.oggvorbis import OggVorbis
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.live_state import begin_step, finish_step, increment, update_current

console = Console()


def process_audio_fx_and_export_ogg(
    input_wav: Path,
    output_ogg: Path,
    race_af_chain: str,
    loudnorm_cfg: Dict,
    ogg_cfg: Dict,
) -> float:
    """
    Runs FFmpeg with race-specific DSP filters + EBU R128 loudnorm + libvorbis q:a 4.
    Returns final OGG duration in seconds.
    """
    output_ogg.parent.mkdir(parents=True, exist_ok=True)

    i_lufs = loudnorm_cfg.get("integrated_lufs", -16.0)
    tp_db = loudnorm_cfg.get("true_peak_db", -1.5)
    lra = loudnorm_cfg.get("lra", 11.0)
    target_sr = ogg_cfg.get("sample_rate", 44100)
    quality = ogg_cfg.get("quality", 4)

    full_af = (
        f"{race_af_chain},"
        f"loudnorm=I={i_lufs}:TP={tp_db}:LRA={lra},"
        f"afade=t=in:st=0:d=0.015"
    )

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

        final_dur = process_audio_fx_and_export_ogg(
            input_wav=raw_wav,
            output_ogg=out_ogg,
            race_af_chain=af_chain,
            loudnorm_cfg=loudnorm_cfg,
            ogg_cfg=ogg_cfg,
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
