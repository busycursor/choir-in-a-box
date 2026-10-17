"""A phone going off in the audience. The ringtones are real ones, dropped
into engine/audience/ringtones/ (any audio file, one ring each); each take is
one of them through a phone's small speaker: it rings once, starts its second
ring, and is grabbed (muffled in a hand for a moment) and cut off.
"""
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
DIR = Path(__file__).resolve().parent.parent / 'engine' / 'audience' / 'ringtones'
LONGEST = 8.0    # seconds of a ringtone file that count as its one ring
GAP = 0.6        # seconds between rings


def tones() -> list[Path]:
    return sorted(f for f in DIR.glob('*') if f.suffix.lower() in ('.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.caf', '.aiff', '.m4r'))


def ring(f: Path) -> np.ndarray:
    """One ring of a ringtone file: mono, its silences trimmed, at most LONGEST seconds."""
    x, _ = librosa.load(f, sr=SR, mono=True)
    x, _ = librosa.effects.trim(x, top_db=45)
    if len(x) > LONGEST * SR:
        x = x[:int(LONGEST * SR)]
        k = int(0.3 * SR); x[-k:] *= np.linspace(1, 0, k)
    return np.concatenate([x, np.zeros(int(GAP * SR))])


def speaker(x: np.ndarray) -> np.ndarray:
    """Through a phone's small speaker: no bass, a soft top, driven a little hard."""
    x = sosfilt(butter(2, [550, 6500], 'bandpass', fs=SR, output='sos'), x)
    x = np.tanh(1.8 * x / max(np.abs(x).max(), 1e-9))
    return x / np.abs(x).max()


def call(f: Path, seed: int = 0) -> np.ndarray:
    """One ring, the start of the second, then grabbed and cut: a moment
    muffled in a hand, getting quieter, and gone."""
    rng = np.random.default_rng(seed)
    one = ring(f)
    second = rng.uniform(0.45, 0.8)                 # seconds of the second ring before a hand gets to it
    grab = 0.22                                     # muffled for this long, then cut
    x = speaker(np.concatenate([one, one[:int((second + grab) * SR)]]))
    i = len(x) - int(grab * SR)
    muffled = sosfilt(butter(2, 450, 'lowpass', fs=SR, output='sos'), x[i - int(0.05 * SR):])[int(0.05 * SR):]
    x[i:] = muffled * 1.6 * np.linspace(1, 0.35, len(muffled))
    x[-int(0.004 * SR):] *= np.linspace(1, 0, int(0.004 * SR))   # cut off: a few milliseconds, no click
    x = np.concatenate([np.zeros(int(0.05 * SR)), x, np.zeros(int(0.3 * SR))])
    return np.stack([x, x], 1) * 10 ** (-1 / 20)
