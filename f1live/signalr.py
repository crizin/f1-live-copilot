"""SignalR Core client for F1 Live Timing.

F1 serves live timing over ASP.NET Core SignalR at /signalrcore. The feed is open:
negotiate over HTTP, upgrade to WebSocket, send the SignalR Core handshake, then
invoke Subscribe with the topics of interest.
"""

import asyncio
import json
import logging

import requests
import websockets

logger = logging.getLogger("f1live.signalr")

SIGNALR_URL = "https://livetiming.formula1.com/signalrcore"
WS_URL = "wss://livetiming.formula1.com/signalrcore"
RS = "\x1e"  # SignalR Core record separator (0x1e)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://www.formula1.com",
    "Accept-Encoding": "gzip, identity",
}

TOPICS_TIMING = [
    "TimingData",
    "TimingAppData",
    "TimingStats",
    "DriverList",
    "DriverRaceInfo",
    "LapCount",
    "SessionInfo",
    "SessionData",
    "TrackStatus",
    "RaceControlMessages",
    "TeamRadio",
    "WeatherData",
    "ExtrapolatedClock",
    "TopThree",
    "Heartbeat",
]

TOPICS_TELEMETRY = [
    "Position.z",
    "CarData.z",
]

TOPICS = TOPICS_TIMING


def _negotiate(session: requests.Session) -> str:
    url = f"{SIGNALR_URL}/negotiate?negotiateVersion=1"
    resp = session.post(url, timeout=15)
    resp.raise_for_status()
    return resp.json()["connectionToken"]


def _build_subscribe_message(topics: list[str]) -> str:
    return json.dumps({
        "type": 1,
        "invocationId": "0",
        "target": "Subscribe",
        "arguments": [topics],
    }) + RS


async def _keepalive(ws):
    """Send SignalR Core ping frames so the server doesn't drop us."""
    try:
        while True:
            await asyncio.sleep(10)
            await ws.send(json.dumps({"type": 6}) + RS)
    except Exception:
        pass


async def connect_and_stream(callback, topics: list[str] | None = None, timeout: int = 300):
    """Connect to F1 SignalR Core and stream messages to callback.

    callback: async function(topic: str, data: dict, timestamp: str | None)
    timeout: seconds without data before disconnecting
    """
    if topics is None:
        topics = TOPICS

    session = requests.Session()
    session.headers.update(HEADERS)

    while True:
        try:
            logger.info("Negotiating connection (SignalR Core)...")
            conn_token = _negotiate(session)
            cookie_str = "; ".join(f"{k}={v}" for k, v in session.cookies.items())
            extra_headers = {"Origin": HEADERS["Origin"], "Cookie": cookie_str}
            ws_url = f"{WS_URL}?id={conn_token}"

            logger.info("Connecting to WebSocket...")
            async with websockets.connect(
                ws_url,
                additional_headers=extra_headers,
                user_agent_header=HEADERS["User-Agent"],
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
            ) as ws:
                # SignalR Core handshake
                await ws.send('{"protocol":"json","version":1}' + RS)
                await asyncio.wait_for(ws.recv(), timeout=15)

                logger.info("Connected! Subscribing to topics...")
                await ws.send(_build_subscribe_message(topics))

                ping_task = asyncio.create_task(_keepalive(ws))
                last_data_time = asyncio.get_event_loop().time()

                try:
                    async for raw_msg in ws:
                        if not raw_msg:
                            continue
                        for frame in raw_msg.split(RS):
                            if not frame.strip():
                                continue
                            try:
                                data = json.loads(frame)
                            except json.JSONDecodeError:
                                continue

                            mtype = data.get("type")

                            # Streaming feed update
                            if mtype == 1 and data.get("target") == "feed":
                                args = data.get("arguments", [])
                                if len(args) >= 2:
                                    topic = args[0]
                                    content = args[1]
                                    ts = args[2] if len(args) > 2 else None
                                    last_data_time = asyncio.get_event_loop().time()
                                    try:
                                        await callback(topic, content, ts)
                                    except Exception:
                                        logger.exception(f"Error in callback for {topic}")

                            # Initial snapshot (completion of Subscribe invocation)
                            elif mtype == 3 and isinstance(data.get("result"), dict):
                                last_data_time = asyncio.get_event_loop().time()
                                for topic, content in data["result"].items():
                                    if topic in topics:
                                        try:
                                            await callback(topic, content, None)
                                        except Exception:
                                            logger.exception(f"Error in callback for initial {topic}")

                        if asyncio.get_event_loop().time() - last_data_time > timeout:
                            logger.warning(f"No data for {timeout}s, disconnecting.")
                            return
                finally:
                    ping_task.cancel()

        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            logger.warning(f"Connection lost: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception:
            logger.exception("Unexpected error. Reconnecting in 5s...")
            await asyncio.sleep(5)
