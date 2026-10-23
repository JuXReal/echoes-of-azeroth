#!/usr/bin/env python3
"""
Step 7: Local A/B Listening Comparison & Launchpad Web Server (web/serve.py)
----------------------------------------------------------------------------
Serves the interactive HTML5 A/B comparison & One-Click Launchpad UI (`web/index.html`)
and provides:
  - `GET  /api/playlist`     -> Full JSON metadata of all localized quests, scripts, QA scores & FX
  - `GET  /api/audit`        -> Independent 100-Quest Quality Audit report (`independent_audit_100_report.json`)
  - `GET  /api/job_status`   -> Live status & console log tail of any background pipeline/audit job
  - `POST /api/start_job`    -> Starts a pipeline run or 100-Quest Audit from the Web UI Start Button
  - `GET  /audio/en/<file>`  -> Original English OGG from ChattyLittleNpc_<Expansion>_voiceovers
  - `GET  /audio/de/<file>`  -> Newly synthesized & mastered German OGG from output/final_ogg
  - `GET  /audio/seed/<file>`-> Extracted 24kHz Mono reference WAV voice seed
"""

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from rich.console import Console

console = Console()

# Global background job state for the Web UI Start Button
JOB_LOCK = threading.Lock()
CURRENT_JOB = {
    "running": False,
    "mode": None,
    "expansion": None,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "logs": [],
}


def _run_background_commands(commands: list, project_root: Path, mode: str, expansion: str):
    global CURRENT_JOB
    env = os.environ.copy()
    env["COQUI_TOS_AGREED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    with JOB_LOCK:
        CURRENT_JOB["running"] = True
        CURRENT_JOB["mode"] = mode
        CURRENT_JOB["expansion"] = expansion
        CURRENT_JOB["started_at"] = time.strftime("%H:%M:%S")
        CURRENT_JOB["finished_at"] = None
        CURRENT_JOB["exit_code"] = None
        CURRENT_JOB["logs"] = [f"[{time.strftime('%H:%M:%S')}] Starting job: {mode} ({expansion})..."]

    exit_code = 0
    for cmd in commands:
        with JOB_LOCK:
            CURRENT_JOB["logs"].append(f"\n$ {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            clean_line = line.rstrip()
            if not clean_line:
                continue
            # Filter cosmetic model config notices and raw progress bar fragments
            if "[transformers] Model config: bos_token_id" in clean_line or "[transformers] Model config: eos_token_id" in clean_line:
                continue
            if "Fetching 9 files:" in clean_line:
                continue

            with JOB_LOCK:
                CURRENT_JOB["logs"].append(clean_line)
                if len(CURRENT_JOB["logs"]) > 250:
                    CURRENT_JOB["logs"] = CURRENT_JOB["logs"][-250:]
        proc.wait()
        if proc.returncode != 0:
            exit_code = proc.returncode
            break

    with JOB_LOCK:
        CURRENT_JOB["running"] = False
        CURRENT_JOB["finished_at"] = time.strftime("%H:%M:%S")
        CURRENT_JOB["exit_code"] = exit_code
        CURRENT_JOB["logs"].append(f"\n[{time.strftime('%H:%M:%S')}] Job finished with exit code {exit_code}.")


class ABComparisonHandler(BaseHTTPRequestHandler):
    project_root: Path = Path(".")
    cfg: dict = {}

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data: dict, status: int = 200):
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, file_path: Path, send_body: bool = True):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, f"File not found: {file_path.name}")
            return

        ctype, _ = mimetypes.guess_type(str(file_path))
        if file_path.suffix.lower() == ".ogg":
            ctype = "audio/ogg"
        elif file_path.suffix.lower() == ".wav":
            ctype = "audio/wav"
        elif file_path.suffix.lower() == ".html":
            ctype = "text/html; charset=utf-8"

        size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            try:
                byte_range = range_header.split("=")[1].split("-")
                start = int(byte_range[0]) if byte_range[0] else 0
                end = int(byte_range[1]) if (len(byte_range) > 1 and byte_range[1]) else size - 1
                end = min(end, size - 1)
                length = max(0, end - start + 1)

                self.send_response(206)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                if send_body:
                    with open(file_path, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                return
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if send_body:
            self.wfile.write(file_path.read_bytes())

    def do_HEAD(self):
        self._handle_request(send_body=False)

    def do_GET(self):
        self._handle_request(send_body=True)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/regenerate_entry":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            entry_id = body.get("entry_id")
            if not entry_id:
                self._send_json({"error": "entry_id is required"}, status=400)
                return

            with JOB_LOCK:
                if CURRENT_JOB["running"]:
                    self._send_json({"error": "A job is already running!"}, status=409)
                    return

            script = str(self.project_root / "pipeline" / "regenerate_single.sh")
            cmds = [["bash", script, str(entry_id)]]

            t = threading.Thread(
                target=_run_background_commands,
                args=(cmds, self.project_root, f"regenerate_{entry_id}", "Single Entry"),
                daemon=True,
            )
            t.start()
            self._send_json({"status": "started", "entry_id": entry_id})
            return

        if parsed.path == "/api/start_job":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            expansion = body.get("expansion", "Midnight")
            mode = body.get("mode", "audit_100")

            with JOB_LOCK:
                if CURRENT_JOB["running"]:
                    self._send_json({"error": "A job is already running!"}, status=409)
                    return

            py = str(self.project_root / ".venv" / "bin" / "python")
            if not Path(py).exists():
                py = sys.executable

            if mode == "audit_100":
                cmds = [[py, "pipeline/07_independent_audit_100.py", "--sample-size", "100"]]
            elif mode == "audit_full":
                cmds = [[py, "pipeline/07_independent_audit_100.py", "--sample-size", "0"]]
            elif mode == "pilot_20":
                cmds = [
                    [py, "pipeline/01_addon_analyzer.py", "--expansion", expansion, "--limit", "20"],
                    [py, "pipeline/02_voice_extractor.py"],
                    [py, "pipeline/03_script_agent.py"],
                    [py, "pipeline/04_tts_generator.py"],
                    [py, "pipeline/05_qa_validator.py"],
                    [py, "pipeline/06_audio_fx.py", "--install-to-wow", "--skip-audit"],
                    [py, "pipeline/07_independent_audit_100.py", "--sample-size", "100"],
                ]
            elif mode == "full_expansion":
                cmds = [
                    [py, "pipeline/01_addon_analyzer.py", "--expansion", expansion, "--limit", "0", "--include-gossip", "--scrape-all-quests"],
                    [py, "pipeline/02_voice_extractor.py"],
                    [py, "pipeline/03_script_agent.py"],
                    [py, "pipeline/04_tts_generator.py"],
                    [py, "pipeline/05_qa_validator.py"],
                    [py, "pipeline/06_audio_fx.py", "--install-to-wow", "--skip-audit"],
                    [py, "pipeline/07_independent_audit_100.py", "--sample-size", "100"],
                ]
            else:
                self._send_json({"error": f"Unknown mode: {mode}"}, status=400)
                return

            t = threading.Thread(
                target=_run_background_commands,
                args=(cmds, self.project_root, mode, expansion),
                daemon=True,
            )
            t.start()
            self._send_json({"status": "started", "mode": mode, "expansion": expansion})
            return

        self.send_error(404, "Not found")

    def _handle_request(self, send_body: bool = True):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path in ("/", "/index.html"):
            self._send_file(self.project_root / "web" / "index.html", send_body=send_body)
            return

        if path == "/api/playlist":
            pilot_path = self.project_root / self.cfg["paths"]["data_raw_de_text"] / "midnight_de_pilot_20.json"
            if pilot_path.exists():
                data = json.loads(pilot_path.read_text(encoding="utf-8"))
                self._send_json(data)
            else:
                self._send_json({"error": "Playlist not generated yet."}, status=404)
            return

        if path == "/api/audit":
            audit_path = self.project_root / self.cfg["paths"]["output_qa_reports"] / "independent_audit_100_report.json"
            if audit_path.exists():
                data = json.loads(audit_path.read_text(encoding="utf-8"))
                self._send_json(data)
            else:
                self._send_json({"audited_count": 0, "passed_count": 0, "results": []})
            return

        if path == "/api/job_status":
            with JOB_LOCK:
                self._send_json(dict(CURRENT_JOB))
            return

        if path.startswith("/audio/en/"):
            fname = os.path.basename(path[len("/audio/en/") :])
            en_dir = Path(self.cfg["paths"]["source_pack_dir"]) / "voiceovers"
            self._send_file(en_dir / fname, send_body=send_body)
            return

        if path.startswith("/audio/de/"):
            fname = os.path.basename(path[len("/audio/de/") :])
            de_dir = self.project_root / self.cfg["paths"]["output_final_ogg"]
            self._send_file(de_dir / fname, send_body=send_body)
            return

        if path.startswith("/audio/seed/"):
            fname = os.path.basename(path[len("/audio/seed/") :])
            seed_dir = self.project_root / self.cfg["paths"]["data_reference_voices"]
            for sub in ("per_entry", "unique_npcs", "archetypes"):
                cand = seed_dir / sub / fname
                if cand.exists():
                    self._send_file(cand, send_body=send_body)
                    return
            self.send_error(404, "Voice seed not found")
            return

        self.send_error(404, "Not found")


def main():
    parser = argparse.ArgumentParser(description="Serve A/B Audio Comparison & Launchpad Web UI.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--host", default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    with open(project_root / args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    host = args.host or cfg.get("web", {}).get("host", "127.0.0.1")
    port = args.port or int(cfg.get("web", {}).get("port", 8765))

    ABComparisonHandler.project_root = project_root
    ABComparisonHandler.cfg = cfg

    server = ThreadingHTTPServer((host, port), ABComparisonHandler)
    console.print(f"[bold green]🎙️  Echoes of Azeroth (DE) Studio & Launchpad running at:[/bold green] [bold cyan]http://{host}:{port}[/bold cyan]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down web server...[/yellow]")
        server.server_close()


if __name__ == "__main__":
    main()
