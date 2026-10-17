"""The harpsichord and the piano, played from their recorded notes (VCSL,
fetched by fetch_instruments.py). Each note takes the nearest recorded note
by measured pitch (alternating takes, so repeated notes aren't identical),
retuned by resampling. The harpsichord rings while the key is held, its
string damped at key-up with the recorded release; the piano's recordings
are pedal-down, so a note lasts until the pedal lifts (the next harmony, as
accompany.py hands it over), and it plays softer and darker or louder and
brighter by velocity, as a piano does.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

SR = 24000
ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / 'engine' / 'instruments'
DAMP = {'harpsichord': 0.03, 'piano': 0.18}   # seconds a note takes to stop at key-up (or pedal-up)
# The piano's recorded dynamic layers, picked by how hard a note is played:
# (velocity up to which it's used, its level). The library normalized each
# layer, so the natural step between soft and loud is put back here.
PIANO_LAYERS = [(0.45, 2, -10.0), (0.72, 3, -4.0), (1.01, 4, 0.0)]
RELEASE_DB = -6                               # the harpsichord's key-up sound, under the note


@lru_cache(maxsize=None)
def _map(instrument: str) -> list[dict]:
    f = DIR / instrument / 'map.json'
    if not f.exists():
        raise FileNotFoundError(f'no {instrument} samples: run scripts/install.sh (or python -m chorale.fetch_instruments)')
    return json.loads(f.read_text())


@lru_cache(maxsize=512)
def _load(instrument: str, name: str) -> np.ndarray:
    y, sr = sf.read(DIR / instrument / name, dtype='float32', always_2d=True)
    y = y[:, :2] if y.shape[1] >= 2 else np.repeat(y, 2, axis=1)
    g = np.gcd(SR, sr)
    return resample_poly(y, SR // g, sr // g, axis=0).astype(np.float32)


def _retune(x: np.ndarray, semitones: float) -> np.ndarray:
    if abs(semitones) < 1e-3:
        return x
    ratio = 2 ** (semitones / 12)
    idx = np.arange(0, len(x) - 1, ratio)
    return np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in range(2)], 1)


def _nearest(instrument: str, midi: int, release: bool, turn: int, layer: int | None = None) -> tuple[dict, float]:
    entries = [e for e in _map(instrument) if e['release'] == release]
    if layer is not None and any(e.get('layer') == layer for e in entries):
        entries = [e for e in entries if e.get('layer') == layer]
    best = min(abs(e['midi'] - midi) for e in entries)
    near = [e for e in entries if abs(e['midi'] - midi) == best]
    e = near[turn % len(near)]
    return e, midi - e['midi']


def play(notes: list, instrument: str, seed: int = 0) -> np.ndarray:
    """Stereo sound for a list of accompany.Note on the harpsichord or piano."""
    end = max(n.end for n in notes) + 2.0
    out = np.zeros((int(end * SR), 2))
    turns = {}
    damp = int(DAMP[instrument] * SR)
    for n in sorted(notes, key=lambda n: n.start):
        turns[n.midi] = turns.get(n.midi, -1) + 1 + seed
        layer, layer_db = None, 0.0
        if instrument == 'piano':
            top, layer, layer_db = next(l for l in PIANO_LAYERS if n.velocity <= l[0])
        e, shift = _nearest(instrument, n.midi, False, turns[n.midi], layer)
        x = _retune(_load(instrument, e['file']), shift)
        held = int(max(0.05, n.end - n.start) * SR)
        x = x[:held + damp].copy()
        k = min(damp, len(x))
        x[len(x) - k:] *= np.linspace(1, 0, k)[:, None]
        if instrument == 'piano':   # the layer's own colour, and within it a few dB by touch
            x = x * 10 ** ((layer_db + 6 * (n.velocity - 0.6)) / 20)
        i = int(n.start * SR)
        j = min(len(out), i + len(x))
        out[i:j] += x[:j - i]
        if instrument == 'harpsichord':
            r, rshift = _nearest(instrument, n.midi, True, turns[n.midi])
            y = _retune(_load(instrument, r['file']), rshift) * 10 ** (RELEASE_DB / 20)
            a = int(n.end * SR)
            b = min(len(out), a + len(y))
            out[a:b] += y[:b - a]
    end = len(out)
    while end > 0 and np.abs(out[end - 1]).max() < 1e-5:
        end -= 1
    out = out[:end]
    return out / max(np.abs(out).max(), 1e-9) * 0.9
