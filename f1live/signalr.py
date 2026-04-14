"""Minimal SignalR client for F1 Live Timing."""

import asyncio
import json
import logging
from urllib.parse import urlencode, urlparse, urlunparse

import requests
import websockets

logger = logging.getLogger("f1live.signalr")

SIGNALR_URL = "https://livetiming.formula1.com/signalr"
HEADERS = {
    "User-agent": "BestHTTP",
    "Accept-Encoding": "gzip, identity",
    "Connection": "keep-alive, Upgrade",
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
    "RcmSeries",
    "TeamRadio",
    "WeatherData",
    "ExtrapolatedClock",
    "TopThree",
    "Heartbeat",
    "AudioStreams",
    "ContentStreams",
]

TOPICS_TELEMETRY = [
    "Position.z",
    "CarData.z",
]

TOPICS = TOPICS_TIMING


def _negotiate(session: requests.Session) -> tuple[dict, dict]:
    conn_data = json.dumps([{"name": "Streaming"}])
    query = urlencode({
        "connectionData": conn_data,
        "clientProtocol": "1.5",
    })
    url = f"{SIGNALR_URL}/negotiate?{query}"
    resp = session.get(url)
    resp.raise_for_status()
    return resp.json(), resp.cookies


def _build_ws_url(token: str) -> str:
    conn_data = json.dumps([{"name": "Streaming"}])
    parsed = urlparse(SIGNALR_URL)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = urlunparse((ws_scheme, parsed.netloc, parsed.path, "", "", ""))
    query = urlencode({
        "transport": "webSockets",
        "connectionToken": token,
        "connectionData": conn_data,
        "clientProtocol": "1.5",
    })
    return f"{ws_url}/connect?{query}"


def _build_subscribe_message(topics: list[str]) -> str:
    return json.dumps({
        "H": "Streaming",
        "M": "Subscribe",
        "A": [topics],
        "I": 0,
    })


async def connect_and_stream(callback, topics: list[str] | None = None, timeout: int = 300):
    """Connect to F1 SignalR and stream messages to callback.

    callback: async function(topic: str, data: dict, timestamp: str | None)
    timeout: seconds without data before disconnecting
    """
    if topics is None:
        topics = TOPICS

    session = requests.Session()
    session.headers.update(HEADERS)

    while True:
        try:
            logger.info("Negotiating connection...")
            config, cookies = _negotiate(session)
            ws_url = _build_ws_url(config["ConnectionToken"])

            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            extra_headers = {**HEADERS, "Cookie": cookie_str}

            logger.info("Connecting to WebSocket...")
            async with websockets.connect(
                ws_url,
                additional_headers=extra_headers,
                ping_interval=20,
                ping_timeout=15,
            ) as ws:
                logger.info("Connected! Subscribing to topics...")
                await ws.send(_build_subscribe_message(topics))

                last_data_time = asyncio.get_event_loop().time()

                async for raw_msg in ws:
                    if not raw_msg:
                        continue

                    data = json.loads(raw_msg)

                    messages = data.get("M", [])
                    if messages:
                        last_data_time = asyncio.get_event_loop().time()
                        for msg in messages:
                            if msg.get("M") == "feed":
                                args = msg.get("A", [])
                                if len(args) >= 2:
                                    topic = args[0]
                                    content = args[1]
                                    timestamp = args[2] if len(args) > 2 else None
                                    try:
                                        await callback(topic, content, timestamp)
                                    except Exception:
                                        logger.exception(f"Error in callback for {topic}")

                    if "R" in data and isinstance(data["R"], dict):
                        last_data_time = asyncio.get_event_loop().time()
                        for topic, content in data["R"].items():
                            if topic in topics:
                                try:
                                    await callback(topic, content, None)
                                except Exception:
                                    logger.exception(f"Error in callback for initial {topic}")

                    if asyncio.get_event_loop().time() - last_data_time > timeout:
                        logger.warning(f"No data for {timeout}s, disconnecting.")
                        return

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
            logger.warning(f"Connection lost: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception:
            logger.exception("Unexpected error. Reconnecting in 5s...")
            await asyncio.sleep(5)
