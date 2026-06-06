"""Optional team-radio transcription via OpenAI gpt-audio-1.5.

Active only when OPENAI_API_KEY is set. Every failure mode — no key, openai
or ffmpeg missing, download/API error, unintelligible audio — degrades
silently to None. The radio URL still appears in the snapshot regardless;
this only adds a spoken-words transcript on top when available.
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
import urllib.request

logger = logging.getLogger("f1live.radio")

MODEL = "gpt-audio-1.5"

_GRID_2026 = (
    "Mercedes: Antonelli, Russell. Ferrari: Leclerc, Hamilton. Red Bull: Verstappen, Hadjar. "
    "McLaren: Norris, Piastri. Alpine: Gasly, Colapinto. Haas: Bearman, Ocon. "
    "Racing Bulls: Lawson, Lindblad. Williams: Sainz, Albon. Audi: Hulkenberg, Bortoleto. "
    "Cadillac: Bottas, Perez. Aston Martin: Alonso, Stroll."
)
_SYSTEM = (
    "You transcribe Formula 1 team radio between a driver and their race engineer. "
    "The audio is short, noisy and clipped — use F1 context to resolve unclear words. "
    f"Current grid — {_GRID_2026} "
    "Common terms: box, pit, push, tyres, sector, traffic, DRS, undercut, overcut, "
    "chequered flag, balance, understeer, oversteer, degradation, delta, formation lap. "
    'Respond ONLY with JSON: {"transcript": "<the words spoken verbatim, '
    'or an empty string if unintelligible>"}'
)


def enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _download(url: str, dst: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r, open(dst, "wb") as f:
            f.write(r.read())
        return os.path.getsize(dst) > 0
    except Exception:
        return False


def _to_wav(src: str, dst: str) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
             "-ar", "16000", "-ac", "1", dst],
            check=True, timeout=30,
        )
        return os.path.getsize(dst) > 0
    except Exception:
        return False


def _transcribe_wav(wav: str) -> str | None:
    try:
        from openai import OpenAI
    except Exception:
        return None
    try:
        client = OpenAI()
        b64 = base64.b64encode(open(wav, "rb").read()).decode()
    except Exception:
        return None

    for _ in range(2):  # gpt-audio occasionally returns empty; one retry
        try:
            r = client.chat.completions.create(
                model=MODEL, modalities=["text"],
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": [
                        {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
                        {"type": "text", "text": "Transcribe this radio clip."},
                    ]},
                ],
            )
            out = (r.choices[0].message.content or "").strip()
        except Exception:
            return None
        if not out:
            continue
        try:
            text = (json.loads(out).get("transcript") or "").strip()
        except Exception:
            text = out.strip().strip("`{}").strip()
        if text:
            return text
    return None


def _transcribe_sync(url: str) -> str | None:
    if not enabled() or not url:
        return None
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "radio.mp3")
        wav = os.path.join(d, "radio.wav")
        if not _download(url, mp3):
            return None
        if not _to_wav(mp3, wav):
            return None
        return _transcribe_wav(wav)


async def transcribe(url: str) -> str | None:
    """Transcribe a team-radio clip URL. Returns the transcript or None (silent)."""
    try:
        return await asyncio.to_thread(_transcribe_sync, url)
    except Exception:
        return None
