import asyncio
import json
import math
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - local hardware dependency
    BleakClient = None
    BleakScanner = None

CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DEVICE_NAME = "FALL_ALARM_C3"

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8765
BASE_DIR = Path(__file__).resolve().parent

STATE_TO_STAGE = {
    "NORM": "Normal",
    "DROP": "Fall",
    "IMPT": "Impact",
    "ALRM": "Fall",
    "SOS": "SOS",
}

STATE_TO_ACTION = {
    "NORM": "Normal",
    "DROP": "Freefall detected",
    "IMPT": "Impact detected",
    "ALRM": "Pre-alarm",
    "SOS": "SOS triggered",
}

state_lock = threading.Lock()
sequence_lock = threading.Lock()
state = "NORM"
sample_counter = 0
last_sequence = 0
last_payload = {
    "connected": False,
    "deviceName": DEVICE_NAME,
    "deviceStatus": "Offline",
    "mode": "NORMAL",
    "currentAction": "Normal",
    "stage": "Normal",
    "stateMachineState": "NORM",
    "ax": 0.0,
    "ay": 0.0,
    "az": 0.0,
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0,
    "magnitude": 0.0,
    "gyroMagnitude": 0.0,
    "pitch": 0.0,
    "sampleCount": 0,
    "timestamp": None,
    "sequence": 0,
}
buffer = []


def estimate_pitch(ax, ay, az):
    return math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))


def next_sequence():
    global last_sequence
    with sequence_lock:
        last_sequence += 1
        return last_sequence


def publish_payload(payload):
    global last_payload
    with state_lock:
        last_payload = payload


def get_latest_payload():
    with state_lock:
        return dict(last_payload)


def get_next_state(current_state, acc_mag, sample_count):
    if current_state == "SOS":
        return "SOS"

    if current_state == "ALRM":
        if acc_mag < 0.4:
            return "DROP"
        if acc_mag > 2.5:
            return "IMPT"
        return "ALRM"

    if current_state == "IMPT":
        if acc_mag < 0.4:
            return "DROP"
        if 0.8 <= acc_mag <= 1.25 and sample_count > 5:
            return "NORM"
        return "IMPT"

    if acc_mag < 0.4:
        return "DROP"

    if current_state == "DROP" and acc_mag > 2.5:
        return "IMPT"

    if current_state == "DROP" and 0.8 <= acc_mag <= 1.25 and sample_count > 5:
        return "NORM"

    return "NORM"


def build_payload(*, connected, ax, ay, az, gx, gy, gz, battery=None):
    global state, sample_counter

    acc_mag = math.sqrt(ax * ax + ay * ay + az * az)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    pitch = estimate_pitch(ax, ay, az)
    sample_counter += 1
    state = get_next_state(state, acc_mag, sample_counter)

    payload = {
        **last_payload,
        "connected": connected,
        "deviceStatus": "Connected" if connected else "Offline",
        "mode": {
            "NORM": "NORMAL",
            "DROP": "FREEFALL",
            "IMPT": "IMPACT",
            "ALRM": "PRE ALARM",
            "SOS": "SOS SENT",
        }.get(state, "NORMAL"),
        "currentAction": STATE_TO_ACTION.get(state, "Normal"),
        "stage": STATE_TO_STAGE.get(state, "Normal"),
        "stateMachineState": state,
        "ax": float(ax),
        "ay": float(ay),
        "az": float(az),
        "gx": float(gx),
        "gy": float(gy),
        "gz": float(gz),
        "magnitude": float(acc_mag),
        "gyroMagnitude": float(gyro_mag),
        "pitch": float(pitch),
        "sampleCount": sample_counter,
        "timestamp": time.time(),
        "sequence": next_sequence(),
    }

    if battery is not None:
        payload["battery"] = float(battery)

    return payload


def notification_handler(sender, data):
    try:
        msg = data.decode(errors="replace").strip()
        parts = msg.split(",")

        if len(parts) != 6:
            print("Ignored BLE payload:", msg)
            return

        ax, ay, az, gx, gy, gz = map(float, parts)

        buffer.append([ax, ay, az, gx, gy, gz])
        if len(buffer) > 300:
          buffer.pop(0)

        payload = build_payload(
            connected=True,
            ax=ax,
            ay=ay,
            az=az,
            gx=gx,
            gy=gy,
            gz=gz,
        )
        publish_payload(payload)

        print(
            f"Samples:{sample_counter} | "
            f"AX:{ax:.2f} AY:{ay:.2f} AZ:{az:.2f} | "
            f"GX:{gx:.2f} GY:{gy:.2f} GZ:{gz:.2f} | "
            f"State:{payload['stateMachineState']} | Stage:{payload['stage']}"
        )

    except Exception as exc:
        print("Parse Error:", exc)


class DashboardHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlsplit(self.path)
        req_path = parsed.path

        if req_path in ("/", "/dashboard"):
            self.serve_dashboard()
            return

        if req_path == "/api/status":
            self.send_json(get_latest_payload())
            return

        if req_path == "/events":
            self.stream_events()
            return

        if req_path.startswith("/assets/"):
            self.serve_asset(req_path)
            return

        self.send_error(404, "Not found")

    def serve_dashboard(self):
        content = b""
        dashboard_path = BASE_DIR / "fall-detection-dashboard.html"
        try:
            with open(dashboard_path, "rb") as handle:
                content = handle.read()
        except FileNotFoundError:
            self.send_error(404, "Dashboard file not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_asset(self, req_path):
        rel_path = req_path[len("/assets/"):]
        rel_path = unquote(rel_path).replace("\\", "/")

        if not rel_path or ".." in rel_path.split("/"):
            self.send_error(400, "Invalid asset path")
            return

        asset_path = (BASE_DIR / "assets" / rel_path).resolve()
        assets_root = (BASE_DIR / "assets").resolve()

        if not str(asset_path).startswith(str(assets_root)) or not asset_path.is_file():
            self.send_error(404, "Asset not found")
            return

        content_type, _ = mimetypes.guess_type(str(asset_path))
        if not content_type:
            content_type = "application/octet-stream"

        data = asset_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload):
        content = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_sent_sequence = -1

        while True:
            payload = get_latest_payload()
            sequence = payload.get("sequence", 0)
            if sequence != last_sent_sequence:
                message = f"data: {json.dumps(payload)}\n\n".encode("utf-8")
                self.wfile.write(message)
                self.wfile.flush()
                last_sent_sequence = sequence
            time.sleep(0.05)

    def log_message(self, format, *args):
        return


def start_http_server():
    server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Dashboard stream ready: http://{HTTP_HOST}:{HTTP_PORT}/events")
    print(f"Dashboard page ready:   http://{HTTP_HOST}:{HTTP_PORT}/")
    return server


async def run_offline_loop():
    while True:
        publish_payload(
            {
                **get_latest_payload(),
                "connected": False,
                "deviceStatus": "Offline",
                "sequence": next_sequence(),
                "timestamp": time.time(),
            }
        )
        print("Bleak not installed. Running dashboard server in offline mode.")
        await asyncio.sleep(5)


async def main():
    start_http_server()

    if BleakClient is None or BleakScanner is None:
        await run_offline_loop()
        return

    while True:
        print("Scanning...")
        devices = await BleakScanner.discover(timeout=10)
        target = next((d for d in devices if d.name == DEVICE_NAME), None)

        if target is None:
            publish_payload(
                {
                    **get_latest_payload(),
                    "connected": False,
                    "deviceStatus": "Offline",
                    "sequence": next_sequence(),
                    "timestamp": time.time(),
                }
            )
            print("ESP32 not found. Retrying in 3 seconds...")
            await asyncio.sleep(3)
            continue

        print("Connecting...")

        try:
            async with BleakClient(target.address) as client:
                publish_payload(
                    {
                        **get_latest_payload(),
                        "connected": True,
                        "deviceStatus": "Connected",
                        "sequence": next_sequence(),
                        "timestamp": time.time(),
                    }
                )
                print("Connected!")

                await client.start_notify(CHAR_UUID, notification_handler)

                while client.is_connected:
                    await asyncio.sleep(1)

        except Exception as exc:
            print("BLE connection lost:", exc)

        publish_payload(
            {
                **get_latest_payload(),
                "connected": False,
                "deviceStatus": "Offline",
                "sequence": next_sequence(),
                "timestamp": time.time(),
            }
        )
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
