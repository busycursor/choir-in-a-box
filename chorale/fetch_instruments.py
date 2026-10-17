"""Download the sampled instruments from the Versilian Community Sample Library
(VCSL, CC0): a Flemish harpsichord (every note it was recorded on, both takes,
and the release sounds) and a Steinway B grand (its pedal-down recordings at
three dynamics, soft, middle and loud: about 730 MB of its 1.3 GB). The organ is synthesized and
needs nothing.

Each instrument's pitch is measured, not read from its file names: the
harpsichord's files are named an octave below what they sound. The offset is
the median over all its samples (a single deep bass note's weak fundamental
can measure an octave off), applied to every file. The result is
engine/instruments/<instrument>/map.json, what sampler.py plays from.

  VCSL: Versilian Studios, CC0. github.com/sgossner/VCSL

Usage: python -m chorale.fetch_instruments   (files already there are skipped)
"""
import http.client, json, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'engine' / 'instruments'
RAW = 'https://raw.githubusercontent.com/sgossner/VCSL/master/'
TREE = 'https://api.github.com/repos/sgossner/VCSL/git/trees/master?recursive=1'
INSTRUMENTS = {
    'harpsichord': ('Chordophones/Zithers/Harpsichord, Flemish/', lambda p: p.endswith('.wav')),
    'piano': ('Chordophones/Zithers/Grand Piano, Steinway B/', lambda p: '/Sus/' in p and '_Close_' in p and re.search(r'_vl[234]_', p)),
}
NAMES = 'C C# D D# E F F# G G# A A# B'.split()


def _get(url: str) -> bytes:
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except (OSError, http.client.HTTPException):
            if attempt == 5:
                raise
            time.sleep(3 * (attempt + 1))


def named_midi(path: str) -> int:
    n = re.search(r'_([A-G]#?)(-?\d)_', Path(path).name)
    return NAMES.index(n.group(1)) + 12 * (int(n.group(2)) + 1)


def measured_midi(file: Path, guess: int) -> int:
    """The sample's pitch: the lowest strong partial, nearest the name or an octave from it."""
    y, sr = sf.read(file)
    y = y.mean(1) if y.ndim > 1 else y
    n = min(len(y) - int(0.05 * sr), sr)
    seg = y[int(0.05 * sr):int(0.05 * sr) + n] * np.hanning(n)
    spec = np.abs(np.fft.rfft(seg)); fr = np.fft.rfftfreq(n, 1 / sr)
    best = None
    for cand in (guess - 12, guess, guess + 12):
        hz = 440 * 2 ** ((cand - 69) / 12)
        k = (fr > hz * 0.97) & (fr < hz * 1.03)
        if k.any():
            level = spec[k].max()
            below = spec[(fr > hz * 0.48) & (fr < hz * 0.52)].max() if hz > 60 else 0
            if level > spec.max() * 0.05 and below < level * 0.3 and (best is None or cand < best):
                best = cand
    return best if best is not None else guess


def fetch(name: str, tree: list) -> Path:
    prefix, want = INSTRUMENTS[name]
    files = [x['path'] for x in tree if x['type'] == 'blob' and x['path'].startswith(prefix) and want(x['path'])]
    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)

    def one(path):
        f = dest / Path(path).name
        if not f.exists():
            f.write_bytes(_get(RAW + urllib.parse.quote(path)))
        return path, f

    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(one, files))
    named = [(path, f, named_midi(path)) for path, f in got]
    shifts = sorted(measured_midi(f, guess) - guess for path, f, guess in named if 'Rel' not in Path(path).name)
    shift = shifts[len(shifts) // 2]
    layer = lambda path: int(m.group(1)) if (m := re.search(r'_vl(\d)_', Path(path).name)) else 0
    entries = [{'file': f.name, 'midi': guess + shift, 'release': 'Rel' in Path(path).name, 'take': Path(path).parent.name,
                'layer': layer(path)} for path, f, guess in named]
    (dest / 'map.json').write_text(json.dumps(sorted(entries, key=lambda e: (e['release'], e['midi'], e['file'])), indent=1) + '\n')
    print(f'{name}: {len(entries)} samples, sounding {shift:+d} semitones from their names', flush=True)
    return dest


def main() -> None:
    tree = json.loads(_get(TREE))['tree']
    for name in INSTRUMENTS:
        fetch(name, tree)


if __name__ == '__main__':
    main()
