import asyncio
import websockets
import time

async def test_telemetry():
    uri = "ws://127.0.0.1:8080/telemetry"
    for _ in range(15):
        try:
            async with websockets.connect(uri) as websocket:
                print("Connected to telemetry endpoint.")
                count = 0
                start_time = time.time()
                while True:
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        count += 1
                    except asyncio.TimeoutError:
                        pass
                    if time.time() - start_time >= 10.0:
                        break
                print(f"Frames received in 10 seconds: {count}")
                return
        except Exception as e:
            print(f"Failed to connect: {e}, retrying in 2 seconds...")
            await asyncio.sleep(2)
    print("Could not connect after retries.")

if __name__ == "__main__":
    asyncio.run(test_telemetry())
