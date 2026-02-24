import os
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, render_template, send_from_directory, jsonify, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(os.environ.get("EWS_BASE_DIR", Path(__file__).resolve().parent))
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
MAPS_DIR = STATIC_DIR / "maps"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MAPS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = DATA_DIR / "weather_log.jsonl"
STATE_FILE = DATA_DIR / "alert_state.json"

app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(BASE_DIR / "templates"))

# --- Helpers ---
def parse_jsonl(path: Path, max_lines: int = 5, days_back: int = None):
    """Read entries from JSONL with optional date filtering."""
    if not path.exists():
        return []
    entries = []
    cutoff = None
    if days_back:
        cutoff = datetime.now() - timedelta(days=days_back)

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if cutoff:
                    # Parse time_wib: "2026-02-24 14:16 WIB"
                    time_str = data.get("time_wib", "").replace(" WIB", "")
                    entry_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                    if entry_time < cutoff:
                        continue
                entries.append(data)
            except Exception:
                continue
    
    if not days_back:
        entries = entries[-max_lines:]
    return entries

def read_latest_log():
    entries = parse_jsonl(LOG_FILE, max_lines=1)
    return entries[0] if entries else None

def read_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def level_from_count(cnt: int):
    if cnt >= 10:
        return "BAHAYA"
    if cnt >= 5:
        return "SIAGA"
    if cnt >= 1:
        return "WASPADA"
    return ""

def color_for_level(level: str):
    # UI color chips
    if level == "BAHAYA":
        return "#e74c3c"  # merah
    if level == "SIAGA":
        return "#e67e22"  # oranye
    if level == "WASPADA":
        return "#f1c40f"  # kuning
    return "#95a5a6"      # abu

@app.route("/")
def index():
    latest = read_latest_log()
    state = read_state()

    # Resolve image path
    latest_map_rel = "maps/latest.jpg"
    latest_map_abs = MAPS_DIR / "latest.jpg"
    if not latest_map_abs.exists() and latest and latest.get("image_path"):
        # fallback ke path dari log
        p = BASE_DIR / latest["image_path"]
        if p.exists():
            latest_map_rel = str(Path(latest["image_path"]).relative_to(STATIC_DIR))

    # Build current alerts
    current_time = None
    current_alerts = []
    if latest:
        current_time = latest.get("time_wib")
        for loc in latest.get("locations", []):
            # If log already included level, use it; else derive from count
            level = loc.get("level") or level_from_count(int(loc.get("count", 0)))
            current_alerts.append({
                "location": loc.get("location"),
                "count": int(loc.get("count", 0)),
                "level": level,
                "dominant_color": loc.get("dominant_color"),
                "weather_warning": loc.get("weather_warning", ""),
                "rgb": loc.get("rgb", [0,0,0]),
                "pixel": loc.get("pixel", [0,0]),
                "chip_color": color_for_level(level)
            })
    else:
        # fallback minimal bila log belum ada: tampilkan dari state.json saja (tanpa detail warna)
        for loc, cnt in sorted(state.items()):
            if int(cnt) > 0:
                level = level_from_count(int(cnt))
                current_alerts.append({
                    "location": loc,
                    "count": int(cnt),
                    "level": level,
                    "dominant_color": None,
                    "weather_warning": "Hujan Lebat - Sangat Lebat" if level else "",
                    "rgb": None,
                    "pixel": None,
                    "chip_color": color_for_level(level)
                })

    # Recent runs (for history list) - Max 5 as requested
    recent_entries = parse_jsonl(LOG_FILE, max_lines=5)

    return render_template(
        "index.html",
        title="AQUA Site Early Warning System Dashboard",
        latest_map_rel=latest_map_rel,
        current_time=current_time,
        current_alerts=current_alerts,
        recent_entries=recent_entries,
        datetime=datetime
    )

@app.route("/run-check", methods=["POST"])
def run_check():
    try:
        subprocess.run(["python3", str(BASE_DIR / "hourly_check.py")], check=True)
        return redirect(url_for("index"))
    except Exception as e:
        return f"Error running check: {e}", 500

@app.route("/reset-alerts", methods=["POST"])
def reset_alerts():
    save_state({})
    # Clear the log file or remove the last entry to clear "Lokasi Terdeteksi"
    if LOG_FILE.exists():
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
    
    # Reset the map by deleting the latest map file
    latest_map = MAPS_DIR / "latest.jpg"
    if latest_map.exists():
        latest_map.unlink()
        
    return redirect(url_for("index"))

@app.route("/history-7d")
def history_7d():
    entries = parse_jsonl(LOG_FILE, days_back=7)
    return render_template(
        "index.html",
        title="AQUA EWS - 7 Day History",
        latest_map_rel=None,
        current_time="7 Day History View",
        current_alerts=[],
        recent_entries=entries,
        datetime=datetime,
        is_history=True
    )

# --- Simple APIs for automation/monitoring ---
@app.route("/api/alerts")
def api_alerts():
    latest = read_latest_log()
    if not latest:
        return jsonify({"ok": True, "data": [], "note": "no logs yet"}), 200
    return jsonify({"ok": True, "data": latest}), 200

@app.route("/api/logs")
def api_logs():
    entries = parse_jsonl(LOG_FILE, max_lines=200)
    return jsonify({"ok": True, "data": entries}), 200

@app.route("/healthz")
def healthz():
    return "ok", 200

# Static maps passthrough if needed (PythonAnywhere will map /static anyway)
@app.route("/maps/<path:filename>")
def maps(filename):
    return send_from_directory(str(MAPS_DIR), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
