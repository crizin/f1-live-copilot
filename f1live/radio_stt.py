"""Optional team-radio transcription via OpenAI gpt-transcribe.

Active only when OPENAI_API_KEY is set. Every failure mode — no key, openai
or ffmpeg missing, download/API error, unintelligible audio — degrades
silently to None. The radio URL still appears in the snapshot regardless;
this only adds a spoken-words transcript on top when available.

A transcription model is used rather than an audio chat model on purpose. Chat models
answer every clip, and on this audio — short, clipped, engine noise over the voice — an
answer is not the same as a transcript: given a grid and a glossary they will compose a
plausible radio call for a clip that contains no speech at all. Returning nothing is the
correct output for an unintelligible clip, so an empty response here is a result, not a
failure, and is never retried.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import urllib.request

logger = logging.getLogger("f1live.radio")

MODEL = "gpt-transcribe"

_GRID_2026 = (
    "Mercedes: Antonelli, Russell. Ferrari: Leclerc, Hamilton. Red Bull: Verstappen, Hadjar. "
    "McLaren: Norris, Piastri. Alpine: Gasly, Colapinto. Haas: Bearman, Ocon. "
    "Racing Bulls: Lawson, Lindblad. Williams: Sainz, Albon. Audi: Hulkenberg, Bortoleto. "
    "Cadillac: Bottas, Perez. Aston Martin: Alonso, Stroll."
)
_PROMPT = (
    "Formula 1 team radio between a driver and their race engineer. Short, noisy, clipped audio. "
    f"Current grid — {_GRID_2026} "
    "Common terms: box, pit, push, tyres, sector, traffic, DRS, undercut, overcut, "
    "chequered flag, balance, understeer, oversteer, degradation, delta, formation lap."
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
        with open(wav, "rb") as f:
            r = client.audio.transcriptions.create(model=MODEL, file=f, prompt=_PROMPT)
    except Exception:
        return None
    return (getattr(r, "text", "") or "").strip() or None


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
