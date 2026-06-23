import asyncio
import numpy as np
import tensorflow as tf
from bleak import BleakScanner, BleakClient

# ----------------------------
# CONFIG
# ----------------------------

CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

MODEL_PATH = "IDP_Fall_Detection/fall_model.keras"
MEAN_PATH = "IDP_Fall_Detection/norm_mean.npy"
STD_PATH = "IDP_Fall_Detection/norm_std.npy"

WINDOW_SIZE = 300
THRESHOLD = 0.57

# Datasheet rule
REQUIRED_CONSECUTIVE_FALLS = 3

# ----------------------------
# LOAD MODEL
# ----------------------------

print("Loading model...")

model = tf.keras.models.load_model(MODEL_PATH)

mean = np.load(MEAN_PATH)
std = np.load(STD_PATH)

print("Model loaded!")

# ----------------------------
# GLOBALS
# ----------------------------

buffer = []

consecutive_falls = 0

state = "NORM"

# ----------------------------
# BLE CALLBACK
# ----------------------------

def notification_handler(sender, data):

    global buffer
    global consecutive_falls
    global state

    try:

        msg = data.decode().strip()

        parts = msg.split(",")

        if len(parts) != 6:
            return

        ax, ay, az, gx, gy, gz = map(float, parts)

        acc_mag = np.sqrt(
            ax*ax +
            ay*ay +
            az*az
        )

        gyro_mag = np.sqrt(
            gx*gx +
            gy*gy +
            gz*gz
        )

        sample = [
            ax,
            ay,
            az,
            gx,
            gy,
            gz,
            acc_mag,
            gyro_mag
        ]

        buffer.append(sample)

        if len(buffer) > WINDOW_SIZE:
            buffer.pop(0)

        # Need full 300 samples
        if len(buffer) < WINDOW_SIZE:
            return

        # ----------------------------
        # MODEL INPUT
        # ----------------------------

        window = np.array(buffer, dtype=np.float32)

        window = window.reshape(1, 300, 8)

        window = (window - mean) / std

        prediction = model.predict(
            window,
            verbose=0
        )

        probability = float(prediction[0][0])

        # ----------------------------
        # FALL DECISION
        # ----------------------------

        if probability > THRESHOLD:

            consecutive_falls += 1

        else:

            consecutive_falls = 0

            state = "NORM"

        # ----------------------------
        # STATE MACHINE
        # ----------------------------

        if consecutive_falls >= 1:
            state = "IMPT"

        if consecutive_falls >= 2:
            state = "ALRM"

        if consecutive_falls >= 3:
            state = "SOS"

        print(
            f"Prob={probability:.3f} | "
            f"Falls={consecutive_falls} | "
            f"State={state}"
        )

    except Exception as e:
        print("ERROR:", e)

# ----------------------------
# BLE MAIN
# ----------------------------

async def main():

    print("Scanning...")

    devices = await BleakScanner.discover(timeout=10)

    target = None

    for d in devices:

        if d.name == "FALL_ALARM_C3":
            target = d
            break

    if target is None:

        print("ESP32 not found")

        return

    print("Connecting...")

    async with BleakClient(target.address) as client:

        print("Connected!")

        await client.start_notify(
            CHAR_UUID,
            notification_handler
        )

        while True:
            await asyncio.sleep(1)

asyncio.run(main()) 
