import asyncio
import websockets
import json

async def test_ws():
    async with websockets.connect("ws://127.0.0.1:8080/telemetry?run_id=0&client=test") as websocket:
        msg = await websocket.recv()
        print("Received bytes:", len(msg))
        with open("frame.bin", "wb") as f:
            f.write(msg)
        print("Saved to frame.bin")

asyncio.run(test_ws())
