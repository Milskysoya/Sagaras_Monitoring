#!/usr/bin/env python3
"""
Varuna ASV - Telemetry publisher (jalan di Jetson Orin Nano Super).

Alur:
  Pixhawk (MAVLink) -> script ini -> Supabase tabel `mission_logs`
  Kamera surface/underwater -> upload ke bucket `mission_images`

Mode:
  python telemetry_publisher.py run                 # telemetri nyata dari Pixhawk
  python telemetry_publisher.py run --simulate      # data palsu (tanpa hardware)
  python telemetry_publisher.py run --dry-run       # tidak kirim ke Supabase, hanya print
  python telemetry_publisher.py capture surface     # ambil & upload 1 foto permukaan
  python telemetry_publisher.py capture underwater  # ambil & upload 1 foto bawah air

Dari program vision/misi, cukup:
  from telemetry_publisher import set_score, set_geotag, upload_image
"""
import argparse
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------- konfigurasi
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # JANGAN taruh di frontend
TABLE = os.getenv("SUPABASE_TABLE", "mission_logs")
BUCKET = os.getenv("SUPABASE_BUCKET", "mission_images")

MAVLINK_CONN = os.getenv("MAVLINK_CONN", "/dev/ttyACM0")
MAVLINK_BAUD = int(os.getenv("MAVLINK_BAUD", "115200"))

SEND_INTERVAL = float(os.getenv("SEND_INTERVAL", "1.0"))  # detik

# Kolam: titik asal (pojok kiri-bawah) dan ukuran, untuk konversi GPS -> x,y (0-25)
POOL_ORIGIN_LAT = float(os.getenv("POOL_ORIGIN_LAT", "-7.952100"))
POOL_ORIGIN_LON = float(os.getenv("POOL_ORIGIN_LON", "112.614500"))
POOL_SIZE_M = float(os.getenv("POOL_SIZE_M", "25"))   # panjang sisi kolam (m)
GRID_MAX = 25.0                                       # sumbu chart 0..25

CAM_SURFACE_INDEX = int(os.getenv("CAM_SURFACE_INDEX", "0"))      # Logitech C922
CAM_UNDERWATER_INDEX = int(os.getenv("CAM_UNDERWATER_INDEX", "1"))  # webcam bawah air

STATE_FILE = Path(os.getenv("STATE_FILE", "mission_state.json"))
WIB = timezone(timedelta(hours=7))
MS_TO_KNOT = 1.943844

# ---------------------------------------------------------------- state misi
_state_lock = threading.Lock()
_state = {"score": 0, "geotag": "Waiting for data...", "position": "--"}


def set_score(value: int) -> None:
    with _state_lock:
        _state["score"] = int(value)


def add_score(delta: int) -> None:
    with _state_lock:
        _state["score"] += int(delta)


def set_geotag(text: str) -> None:
    with _state_lock:
        _state["geotag"] = text


def set_position_label(label: str) -> None:
    with _state_lock:
        _state["position"] = label


def _load_state_file() -> None:
    """Program vision boleh menulis mission_state.json: {"score": 20, "position": "A3"}"""
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return
    with _state_lock:
        for k in ("score", "geotag", "position"):
            if k in data:
                _state[k] = data[k]


# ---------------------------------------------------------------- supabase
_client = None


def get_client():
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY belum diisi (lihat .env.example)")
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def check_connection() -> bool:
    try:
        get_client().table(TABLE).select("id").limit(1).execute()
        print("[OK] Terhubung ke Supabase")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] Gagal terhubung ke Supabase: {e}")
        return False


def send_row(row: dict, dry_run: bool = False) -> bool:
    if dry_run:
        print("[DRY]", json.dumps(row))
        return True
    try:
        get_client().table(TABLE).insert(row).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] Gagal kirim data: {e}")
        return False


def upload_image(frame_or_path, kind: str) -> bool:
    """
    kind: "surface" atau "underwater" (nama file wajib mengandung kata ini,
    karena frontend mencarinya dari nama file).
    frame_or_path: array OpenCV (BGR) atau path file jpg.
    """
    if kind not in ("surface", "underwater"):
        raise ValueError("kind harus 'surface' atau 'underwater'")

    if isinstance(frame_or_path, (str, Path)):
        data = Path(frame_or_path).read_bytes()
    else:
        import cv2
        ok, buf = cv2.imencode(".jpg", frame_or_path, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            print("[ERR] Encode JPEG gagal")
            return False
        data = buf.tobytes()

    name = f"{kind}_{datetime.now(WIB).strftime('%Y%m%d_%H%M%S')}.jpg"
    try:
        get_client().storage.from_(BUCKET).upload(
            name, data, {"content-type": "image/jpeg", "upsert": "true"}
        )
        print(f"[OK] Upload {name} ({len(data) // 1024} KB)")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] Upload gagal: {e}")
        return False


def capture_and_upload(kind: str) -> bool:
    import cv2
    index = CAM_SURFACE_INDEX if kind == "surface" else CAM_UNDERWATER_INDEX
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[ERR] Kamera {kind} (index {index}) tidak bisa dibuka")
        return False
    for _ in range(5):          # buang beberapa frame awal (auto exposure)
        cap.read()
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"[ERR] Gagal membaca frame kamera {kind}")
        return False
    return upload_image(frame, kind)


# ---------------------------------------------------------------- telemetri
def latlon_to_xy(lat: float, lon: float) -> tuple[float, float]:
    """GPS -> koordinat kolam 0..25 (equirectangular, cukup akurat untuk area kecil)."""
    dy = (lat - POOL_ORIGIN_LAT) * 111_320.0
    dx = (lon - POOL_ORIGIN_LON) * 111_320.0 * math.cos(math.radians(POOL_ORIGIN_LAT))
    scale = GRID_MAX / POOL_SIZE_M
    x = min(max(dx * scale, 0.0), GRID_MAX)
    y = min(max(dy * scale, 0.0), GRID_MAX)
    return round(x, 2), round(y, 2)


def build_row(lat, lon, sog_knot, cog_deg) -> dict:
    x, y = latlon_to_xy(lat, lon)
    _load_state_file()
    with _state_lock:
        s = dict(_state)
    now = datetime.now(WIB)
    geotag = f"{now.strftime('%A, %d/%m/%Y %H:%M:%S')}, {lat:.6f}, {lon:.6f}"
    return {
        "sog": round(sog_knot, 2),
        "cog": round(cog_deg % 360, 1),
        "position": s["position"] if s["position"] != "--" else f"{lat:.5f}, {lon:.5f}",
        "geotag": geotag,
        "score": s["score"],
        "x": x,
        "y": y,
        "lat": lat,
        "lon": lon,
    }


class MavlinkSource:
    def __init__(self):
        from pymavlink import mavutil
        print(f"[..] Menghubungkan ke Pixhawk: {MAVLINK_CONN}")
        self.m = mavutil.mavlink_connection(MAVLINK_CONN, baud=MAVLINK_BAUD)
        self.m.wait_heartbeat(timeout=15)
        print("[OK] Heartbeat Pixhawk diterima")
        self.m.mav.request_data_stream_send(
            self.m.target_system, self.m.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_POSITION, 4, 1)
        self.last = None

    def read(self):
        # kosongkan buffer, ambil pesan GLOBAL_POSITION_INT terbaru
        msg = None
        while True:
            m = self.m.recv_match(type="GLOBAL_POSITION_INT", blocking=(msg is None), timeout=2)
            if m is None:
                break
            msg = m
        if msg is None:
            return self.last
        lat, lon = msg.lat / 1e7, msg.lon / 1e7
        vx, vy = msg.vx / 100.0, msg.vy / 100.0          # m/s
        sog = math.hypot(vx, vy) * MS_TO_KNOT
        if math.hypot(vx, vy) > 0.3:                      # COG dari vektor kecepatan
            cog = math.degrees(math.atan2(vy, vx)) % 360
        else:                                             # diam: pakai heading kapal
            cog = (msg.hdg / 100.0) if msg.hdg != 65535 else 0.0
        self.last = (lat, lon, sog, cog)
        return self.last


class SimulatedSource:
    """Kapal berputar mengelilingi kolam, untuk tes tanpa hardware."""

    def __init__(self):
        self.t0 = time.time()

    def read(self):
        t = time.time() - self.t0
        ang = t / 20.0
        cx = cy = POOL_SIZE_M / 2
        r = POOL_SIZE_M * 0.35
        px, py = cx + r * math.cos(ang), cy + r * math.sin(ang)
        lat = POOL_ORIGIN_LAT + py / 111_320.0
        lon = POOL_ORIGIN_LON + px / (111_320.0 * math.cos(math.radians(POOL_ORIGIN_LAT)))
        speed = r / 20.0
        cog = (math.degrees(ang) + 90) % 360
        return lat, lon, speed * MS_TO_KNOT, cog


def run(args) -> None:
    if not args.dry_run and not check_connection():
        sys.exit(1)
    source = SimulatedSource() if args.simulate else MavlinkSource()
    print(f"[..] Mengirim telemetri tiap {SEND_INTERVAL}s. Ctrl+C untuk berhenti.")
    fail = 0
    try:
        while True:
            t0 = time.time()
            sample = source.read()
            if sample is None:
                print("[WARN] Belum ada data GPS dari Pixhawk")
            else:
                ok = send_row(build_row(*sample), dry_run=args.dry_run)
                fail = 0 if ok else fail + 1
                if fail >= 10:
                    print("[WARN] 10x gagal berturut-turut, cek koneksi internet/Wi-Fi")
                    fail = 0
            time.sleep(max(0.0, SEND_INTERVAL - (time.time() - t0)))
    except KeyboardInterrupt:
        print("\n[OK] Berhenti.")


def main() -> None:
    p = argparse.ArgumentParser(description="Varuna telemetry publisher")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--simulate", action="store_true", help="data palsu, tanpa Pixhawk")
    r.add_argument("--dry-run", action="store_true", help="print saja, tidak kirim ke Supabase")
    c = sub.add_parser("capture")
    c.add_argument("kind", choices=["surface", "underwater"])
    args = p.parse_args()

    if args.cmd == "run":
        run(args)
    else:
        sys.exit(0 if capture_and_upload(args.kind) else 1)


if __name__ == "__main__":
    main()
