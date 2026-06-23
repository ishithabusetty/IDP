import asyncio
# from curses import window
import numpy as np
from bleak import BleakScanner, BleakClient

CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

buffer = []

def notification_handler(sender, data):
    global buffer

    try:
        msg = data.decode().strip()

        parts = msg.split(",")

        if len(parts) != 6:
            return

        ax, ay, az, gx, gy, gz = map(float, parts)

        acc_mag = np.sqrt(ax*ax + ay*ay + az*az)
        gyro_mag = np.sqrt(gx*gx + gy*gy + gz*gz)

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

        if len(buffer) > 300:
            buffer.pop(0)

        print(
            f"Samples:{len(buffer)} | "
            f"AX:{ax:.2f} AY:{ay:.2f} AZ:{az:.2f} | "
            f"GX:{gx:.2f} GY:{gy:.2f} GZ:{gz:.2f}"
        )

        if len(buffer) == 300:

            window = np.array(buffer)

            print("\n========================")
            print("WINDOW READY")
            print("Shape:", window.shape)
            print("Last Sample:", window[-1])
            print("========================\n")

            buffer.clear()

    except Exception as e:
        print("Parse Error:", e)


async def main():

    devices = await BleakScanner.discover(timeout=10)

    target = None

    for d in devices:
        if d.name == "FALL_ALARM_C3":
            target = d
            break

    if target is None:
        print("ESP32 not found")
        return

    async with BleakClient(target.address) as client:

        print("Connected")

        await client.start_notify(
            CHAR_UUID,
            notification_handler
        )

        while True:
            await asyncio.sleep(1)


asyncio.run(main())