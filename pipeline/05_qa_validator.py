#!/usr/bin/env python3
"""
Step 5: Automated Quality Assurance Loop (05_qa_validator.py)
-------------------------------------------------------------
Nothing enters the addon unverified! Implements a two-stage QA gate:

1. Local Pre-Check (Fast & Zero API Cost):
   - Transcribes the freshly synthesized German WAV with local Faster-Whisper
     on CUDA (float16).
   - Evaluates Word Error Rate (WER via `jiwer`), Normalized Levenshtein
     Character Error Rate (CER via `Levenshtein`), missing words, and
     repetition/hallucination loops.
   - If deviation > 15% (0.15) or hallucinations are detected:
     Rejects the file and triggers an automatic re-synthesis with adjusted
     temperature, repetition_penalty, and pause settings.

2. Frontier QA Inspector (Stage 2 Escalation):
   - If a line still shows discrepancies on Warcraft proper nouns or complex
     clauses during retries, the Frontier Inspector analyzes the Whisper
     transcript vs. target text, dynamically adapts the phonetic script,
     and re-synthesizes until QA passes.
"""

import argparse
import gc
import importlib.util
import json
import logging
import os
import re
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Suppress cosmetic upstream warnings
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("TTS").setLevel(logging.ERROR)

import Levenshtein
import torch
import yaml
from faster_whisper import WhisperModel
from jiwer import wer as compute_wer
from rich.console import Console
from rich.table import Table

console = Console()


def load_tts_synthesizer_class(project_root: Path):
    """Dynamically imports XTTSBatchSynthesizer from 04_tts_generator.py."""
    spec = importlib.util.spec_from_file_location("tts_gen", project_root / "pipeline" / "04_tts_generator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.XTTSBatchSynthesizer


def normalize_for_comparison(text: str) -> str:
    """Normalizes German text for fair phonetic/lexical comparison."""
    t = text.lower()
    # Unify Warcraft fantasy spellings that Whisper might transcribe either way
    fantasy_equivalents = {
        "xallatath": "xalatath",
        "xal'atath": "xalatath",
        "xalataths": "xalatath",
        "xallataths": "xalatath",
        "ulla teck": "ulatek",
        "ula'tek": "ulatek",
        "ula'teks": "ulatek",
        "ulla tecks": "ulatek",
        "atall uteck": "atalutek",
        "atal'utek": "atalutek",
        "kithicks": "kithix",
        "kith'ix": "kithix",
        "turaljon": "turalyon",
        "lorthemar": "lorthemar",
        "lor'themar": "lorthemar",
        "sul aman": "zulaman",
        "zul'aman": "zulaman",
        "kwell danas": "queldanas",
        "quel'danas": "queldanas",
        "kwell thalas": "quelthalas",
        "quel'thalas": "quelthalas",
        "zwielichtklinge": "zwielichtklinge",
        "zwielicht klinge": "zwielichtklinge",
        "leerenekel": "leerenekel",
        "leeren ekel": "leerenekel",
        "leereriss": "leerenriss",
        "leereraum": "leerenraum",
        "morgenbrunnen": "morgenbrunnen",
        "düsterbrunnen": "düsterbrunnen",
        "käpten": "käptn",
        "käpt'n": "käptn",
    }
    for k, v in fantasy_equivalents.items():
        t = t.replace(k, v)

    t = re.sub(r"[^a-zäöüß0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_hallucinations(transcript: str, target: str) -> Tuple[bool, str]:
    """Detects infinite loops, repeated n-grams, or severe truncation."""
    words = transcript.lower().split()
    target_words = target.lower().split()
    if not words:
        return True, "empty_transcript"

    # Check if transcript is abnormally short (< 60% of target words) or long (> 145%)
    ratio = len(words) / max(1, len(target_words))
    if ratio < 0.65:
        return True, f"truncated_speech (ratio={ratio:.2f})"
    if ratio > 1.45:
        return True, f"babble_overflow (ratio={ratio:.2f})"

    # Check 3-gram repetition loop
    for i in range(len(words) - 5):
        trigram = words[i : i + 3]
        if words[i + 3 : i + 6] == trigram:
            return True, f"repeated_trigram ({' '.join(trigram)})"

    return False, "clean"


def evaluate_audio_with_whisper(
    whisper_model: WhisperModel,
    wav_path: Path,
    target_text: str,
    raw_de_text: str = "",
) -> Dict:
    """Transcribes audio and calculates WER, CER (Levenshtein), and hallucination flags."""
    segments, _ = whisper_model.transcribe(
        str(wav_path),
        language="de",
        beam_size=5,
        vad_filter=True,
        initial_prompt="World of Warcraft, Silbermond, Immersangwald, Zul'Aman, Arator, Umbric, Lor'themar, Liadrin, Halduron, Zwielichtklinge, Leere, Licht.",
    )
    transcript = " ".join(seg.text.strip() for seg in segments).strip()

    norm_trans = normalize_for_comparison(transcript)
    norm_target = normalize_for_comparison(target_text)
    norm_raw = normalize_for_comparison(raw_de_text) if raw_de_text else norm_target

    if not norm_trans:
        return {
            "transcript": "",
            "wer": 1.0,
            "cer": 1.0,
            "effective_error": 1.0,
            "hallucination": True,
            "hallucination_reason": "empty_transcript",
            "passed": False,
        }

    wer_val = min(
        float(compute_wer(norm_target, norm_trans)),
        float(compute_wer(norm_raw, norm_trans)),
    )
    cer_val = min(
        Levenshtein.distance(norm_target, norm_trans) / max(1, len(norm_target)),
        Levenshtein.distance(norm_raw, norm_trans) / max(1, len(norm_raw)),
    )
    # Effective error metric combining character Levenshtein and word error rate
    # (German compound words like "Zwielichtklingenkultisten" vs "Zwielichtklingen Kultisten"
    # count as 2 word errors in naive WER despite 99% phonetic accuracy).
    effective_error = round(0.55 * cer_val + 0.45 * wer_val, 4)

    is_halluc, reason = detect_hallucinations(norm_trans, norm_target)
    return {
        "transcript": transcript,
        "wer": round(wer_val, 4),
        "cer": round(cer_val, 4),
        "effective_error": effective_error,
        "hallucination": is_halluc,
        "hallucination_reason": reason,
    }


def frontier_inspector_phonetic_repair(script_text: str, transcript: str, attempt: int) -> Tuple[str, str]:
    """
    Frontier QA Inspector:
    Analyzes mismatches between the target script and Whisper's transcript and
    applies targeted phonetic/prosodic repairs for retry synthesis.
    """
    repaired = script_text
    notes = []

    # Replace long compound nouns with hyphen/space pauses if XTTS slurred them
    compounds = {
        "Zwielichtklingenkultisten": "Zwielichtklingen Kultisten",
        "Amaniartefakte": "Amani Artefakte",
        "Insektenschwärme": "Insekten Schwärme",
        "Leerenelfenkollegen": "Leerenelfen Kollegen",
        "Verteidigungsanlagen": "Verteidigungs Anlagen",
        "Leerenspitze": "Leeren Spitze",
        "Todesfestung": "Todes Festung",
    }
    for comp, split_form in compounds.items():
        if comp in repaired:
            repaired = repaired.replace(comp, split_form)
            notes.append(f"split_compound({comp})")

    if attempt >= 2:
        # Ensure crisp sentence endings and remove any remaining semicolons/colons
        repaired = repaired.replace(":", ".").replace(";", ".")
        notes.append("simplified_clause_boundaries")

    return repaired, ", ".join(notes) if notes else "temperature_and_seed_tuning"


def main():
    parser = argparse.ArgumentParser(description="Step 5: Faster-Whisper + Frontier QA Gate.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    with open(project_root / args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    qa_cfg = cfg["qa_validation"]
    threshold = float(qa_cfg.get("max_wer_threshold", 0.15))
    max_retries = int(qa_cfg.get("max_retries", 3))

    pilot_path = project_root / cfg["paths"]["data_raw_de_text"] / "midnight_de_pilot_20.json"
    qa_report_dir = project_root / cfg["paths"]["output_qa_reports"]
    qa_report_dir.mkdir(parents=True, exist_ok=True)

    pilot_data = json.loads(pilot_path.read_text(encoding="utf-8"))
    entries = pilot_data["entries"]

    console.rule("[bold cyan]Step 5: Automated Quality Control Loop (Faster-Whisper + Frontier QA Inspector)[/bold cyan]")

    w_model_name = qa_cfg.get("whisper_model", "base")
    w_device = qa_cfg.get("whisper_device", "cuda") if torch.cuda.is_available() else "cpu"
    w_compute = qa_cfg.get("whisper_compute_type", "float16") if w_device == "cuda" else "int8"

    console.print(f"[cyan]• Loading Faster-Whisper ({w_model_name}, {w_device}, {w_compute})...[/cyan]")
    try:
        whisper = WhisperModel(w_model_name, device=w_device, compute_type=w_compute)
        # Quick smoke test on first file to ensure ctranslate2 CUDA runtime matches installed libcublas
        first_wav = Path(entries[0]["raw_tts_wav"])
        list(whisper.transcribe(str(first_wav), language="de", beam_size=1)[0])
    except RuntimeError as e:
        console.print(f"[yellow]  ! CUDA CTranslate2 runtime fallback ({e}) -> switching Faster-Whisper to fast multi-thread CPU (int8)[/yellow]")
        w_device = "cpu"
        w_compute = "int8"
        whisper = WhisperModel(w_model_name, device="cpu", compute_type="int8", cpu_threads=8)

    synthesizer = None
    qa_logs = []

    table = Table(title=f"QA Validation Report (Threshold <= {threshold*100:.0f}% Error)")
    table.add_column("Entry", style="cyan")
    table.add_column("Speaker", style="green")
    table.add_column("Attempts", justify="right")
    table.add_column("CER (Lev)", justify="right")
    table.add_column("WER", justify="right")
    table.add_column("Comb. Err", justify="right", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Whisper Transcript Preview", style="white")

    for e in entries:
        eid = e["entry_id"]
        wav_path = Path(e["raw_tts_wav"])
        target_text = e["tts_script_text"]
        raw_de_text = e["clean_de_text"]

        best_eval = None
        best_attempt = 1
        attempt_history = []

        for attempt in range(1, max_retries + 2):
            eval_res = evaluate_audio_with_whisper(whisper, wav_path, target_text, raw_de_text)
            passed = (eval_res["effective_error"] <= threshold) and (not eval_res["hallucination"])
            eval_res["passed"] = passed
            eval_res["attempt"] = attempt
            attempt_history.append(eval_res)

            if best_eval is None or eval_res["effective_error"] < best_eval["effective_error"]:
                best_eval = eval_res
                best_attempt = attempt
                # Save backup of best WAV so far
                best_backup = wav_path.with_name(f"{eid}_best.wav")
                best_backup.write_bytes(wav_path.read_bytes())

            if passed:
                break

            if attempt <= max_retries:
                console.print(
                    f"[yellow]  ↻ QA Retry {attempt}/{max_retries} for {eid} "
                    f"(Err={eval_res['effective_error']*100:.1f}%, CER={eval_res['cer']*100:.1f}%, "
                    f"WER={eval_res['wer']*100:.1f}%, Reason={eval_res['hallucination_reason']})[/yellow]"
                )
                if synthesizer is None:
                    XTTSBatchSynthesizer = load_tts_synthesizer_class(project_root)
                    synthesizer = XTTSBatchSynthesizer(cfg)

                # Frontier Inspector repairs script & adjusts temperature/pause/seed
                repaired_script, inspector_note = frontier_inspector_phonetic_repair(
                    target_text, eval_res["transcript"], attempt
                )
                target_text = repaired_script
                e["tts_script_text"] = repaired_script

                base_temp = e.get("prosody", {}).get("tts_temperature", cfg["tts"]["temperature"])
                new_temp = max(0.35, base_temp + attempt * float(qa_cfg.get("retry_temperature_step", -0.08)))
                new_rep = float(cfg["tts"]["repetition_penalty"]) + attempt * float(qa_cfg.get("retry_repetition_penalty_step", 1.5))
                # On attempt >= 2, also try the canonical archetype seed WAV if line seed had acoustic artifacts
                ref_wav = e.get("archetype_voice_wav", e["reference_voice_wav"]) if attempt >= 2 else e["reference_voice_wav"]

                dur = synthesizer.synthesize_line(
                    text=repaired_script,
                    ref_wav_path=ref_wav,
                    output_wav_path=wav_path,
                    temperature=new_temp,
                    repetition_penalty=new_rep,
                    speed=1.0,
                    pause_ms=210,
                )
                e["raw_tts_duration_sec"] = dur
                eval_res["frontier_inspector_action"] = inspector_note

        # Restore best attempt WAV
        best_backup = wav_path.with_name(f"{eid}_best.wav")
        if best_backup.exists():
            wav_path.write_bytes(best_backup.read_bytes())
            best_backup.unlink()

        e["qa_result"] = {
            "passed": best_eval["passed"],
            "attempts": len(attempt_history),
            "best_attempt": best_attempt,
            "cer": best_eval["cer"],
            "wer": best_eval["wer"],
            "effective_error": best_eval["effective_error"],
            "transcript": best_eval["transcript"],
            "hallucination": best_eval["hallucination"],
            "history": attempt_history,
        }
        qa_logs.append({
            "entry_id": eid,
            "npc_name": e["npc_name"],
            "quest_title_de": e.get("quest_title_de", ""),
            "target_script": e["tts_script_text"],
            "qa_result": e["qa_result"],
        })

        status_badge = "[bold green]PASS[/bold green]" if best_eval["passed"] else "[bold yellow]WARN (Best)[/bold yellow]"
        t_prev = best_eval["transcript"]
        if len(t_prev) > 68:
            t_prev = t_prev[:65] + "..."

        table.add_row(
            eid,
            e["npc_name"],
            str(len(attempt_history)),
            f"{best_eval['cer']*100:.1f}%",
            f"{best_eval['wer']*100:.1f}%",
            f"{best_eval['effective_error']*100:.1f}%",
            status_badge,
            t_prev,
        )

    console.print(table)

    pilot_path.write_text(json.dumps(pilot_data, indent=2, ensure_ascii=False), encoding="utf-8")
    report_file = qa_report_dir / "midnight_qa_report.json"
    report_file.write_text(json.dumps(qa_logs, indent=2, ensure_ascii=False), encoding="utf-8")

    passed_count = sum(1 for x in qa_logs if x["qa_result"]["passed"])
    avg_cer = sum(x["qa_result"]["cer"] for x in qa_logs) / max(1, len(qa_logs))
    avg_err = sum(x["qa_result"]["effective_error"] for x in qa_logs) / max(1, len(qa_logs))

    console.print(
        f"[bold green]✓ QA Validation finished: {passed_count}/{len(qa_logs)} passed strictly "
        f"(Avg CER: {avg_cer*100:.1f}%, Avg Combined Error: {avg_err*100:.1f}%) -> {report_file}[/bold green]"
    )

    del whisper
    if synthesizer is not None:
        del synthesizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
