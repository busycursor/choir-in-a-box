"""A synthesized pipe organ: three divisions (Great, an enclosed Swell, Pedal),
stops built from the way pipes of each family sound, couplers, a swell box, a
tremulant, and named registrations.

Pipes are steady tones, which is why an organ synthesizes well: each pipe here
is its family's harmonic spectrum (principals: a strong fundamental and second
harmonic falling away steadily; open flutes: nearly pure; stopped flutes:
mostly odd harmonics, the hollow sound; strings: many harmonics, slow to
speak; trumpets: brightest around the third harmonic; oboes: a weak
fundamental), plus how it speaks (each family's attack, a little chiff on
principals and open flutes) and a breath of wind noise. Every pipe is
slightly out of tune with its neighbours, by a seeded amount per stop and
note, so the same registration sounds the same every time and a chorus of
stops sounds like pipes, not oscillators. Mixtures are ranks of high
principals that break back an octave as the keys go up; the celeste is tuned
a little sharp to beat against the strings. Pipes stand in the case on a C
side and a C-sharp side, alternating by semitone; the pedal towers are wide.
"""
import zlib
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt

SR = 24000

# harmonic levels in dB, fundamental first
SPECTRA = {
    'principal':  [0, -4, -10, -13, -18, -21, -25, -27, -30, -33, -36, -38],
    'flute':      [0, -15, -24, -32, -38],
    'gedackt':    [0, -32, -11, -36, -21, -40, -29, -44, -35],
    'string':     [-2, 0, -2, -4, -5, -7, -8, -10, -11, -12, -14, -15, -16, -18, -19, -20],
    'trumpet':    [-2, 0, 2, 1, 0, -2, -4, -5, -6, -8, -9, -10, -12, -13, -15, -16, -18, -19],
    'oboe':       [-9, -3, 0, -3, -6, -9, -12, -15, -18, -21],
}
ATTACK = {'principal': 0.045, 'flute': 0.035, 'gedackt': 0.03, 'string': 0.11, 'trumpet': 0.022, 'oboe': 0.03}
CHIFF = {'principal': -20, 'flute': -16, 'gedackt': -24}   # dB, a short breathy burst as the pipe speaks
RELEASE = 0.07
DETUNE_CENTS = 2.0     # each pipe off by up to this much, seeded per stop and note
WIND_DB = -46


def footage_shift(feet: float) -> int:
    """Semitones above unison (8') a footage sounds."""
    return int(round(12 * np.log2(8 / feet)))


@dataclass(frozen=True)
class Stop:
    name: str
    family: str
    feet: tuple            # one footage, or a mixture's ranks
    level_db: float = 0.0
    detune_cents: float = 0.0   # a celeste's sharpness
    breaks: bool = False        # a mixture: ranks break back an octave as the keys rise


GREAT = {
    'Bourdon 16': Stop('Bourdon 16', 'gedackt', (16,), -4),
    'Principal 8': Stop('Principal 8', 'principal', (8,), 0),
    'Rohrflöte 8': Stop('Rohrflöte 8', 'gedackt', (8,), -3),
    'Octave 4': Stop('Octave 4', 'principal', (4,), -3),
    'Spitzflöte 4': Stop('Spitzflöte 4', 'flute', (4,), -5),
    'Quinte 2 2/3': Stop('Quinte 2 2/3', 'principal', (8 / 3,), -9),
    'Superoctave 2': Stop('Superoctave 2', 'principal', (2,), -7),
    'Mixture IV': Stop('Mixture IV', 'principal', (4 / 3, 1, 2 / 3, 1 / 2), -10, breaks=True),
    'Trumpet 8': Stop('Trumpet 8', 'trumpet', (8,), -2),
}
SWELL = {
    'Gedackt 8': Stop('Gedackt 8', 'gedackt', (8,), -2),
    'Salicional 8': Stop('Salicional 8', 'string', (8,), -6),
    'Voix céleste 8': Stop('Voix céleste 8', 'string', (8,), -7, detune_cents=7),
    'Flute 4': Stop('Flute 4', 'flute', (4,), -5),
    'Nazard 2 2/3': Stop('Nazard 2 2/3', 'flute', (8 / 3,), -10),
    'Flageolet 2': Stop('Flageolet 2', 'flute', (2,), -9),
    'Tierce 1 3/5': Stop('Tierce 1 3/5', 'flute', (8 / 5,), -12),
    'Oboe 8': Stop('Oboe 8', 'oboe', (8,), -4),
}
PEDAL = {
    'Subbass 16': Stop('Subbass 16', 'gedackt', (16,), 0),
    'Violone 16': Stop('Violone 16', 'string', (16,), -5),
    'Octavebass 8': Stop('Octavebass 8', 'principal', (8,), -4),
    'Choralbass 4': Stop('Choralbass 4', 'principal', (4,), -8),
    'Posaune 16': Stop('Posaune 16', 'trumpet', (16,), -3),
}
DIVISIONS = {'great': GREAT, 'swell': SWELL, 'pedal': PEDAL}


@dataclass
class Registration:
    """Which stops are drawn, the couplers, the swell box and the tremulant."""
    great: tuple = ()
    swell: tuple = ()
    pedal: tuple = ()
    swell_to_great: bool = False
    great_to_pedal: bool = False
    swell_to_pedal: bool = False
    swell_octave: bool = False      # Swell 4': each Swell note also an octave up
    swell_suboctave: bool = False   # Swell 16'
    swell_box: float = 0.7          # 0 shut .. 1 open
    tremulant: bool = False


REGISTRATIONS = {
    # accompanying a choir: soft 8' and 4' flutes, a quiet 16' and 8' under them
    'continuo': Registration(swell=('Gedackt 8', 'Flute 4'), pedal=('Subbass 16', 'Octavebass 8'), swell_box=0.6),
    # a fuller chorale accompaniment: principals 8' and 4', the Swell coupled, pedal 16' and 8'
    'chorale': Registration(great=('Principal 8', 'Octave 4'), swell=('Gedackt 8', 'Flute 4'), pedal=('Subbass 16', 'Octavebass 8'),
                            swell_to_great=True, great_to_pedal=True, swell_box=0.7),
    # quiet and warm: the strings and their celeste, the box half shut
    'soft': Registration(swell=('Gedackt 8', 'Salicional 8', 'Voix céleste 8'), pedal=('Subbass 16',), swell_to_pedal=True, swell_box=0.45),
    # the full principal chorus (organo pleno), with the pedal reed
    'plenum': Registration(great=('Bourdon 16', 'Principal 8', 'Octave 4', 'Quinte 2 2/3', 'Superoctave 2', 'Mixture IV'),
                           swell=('Gedackt 8', 'Flute 4', 'Flageolet 2'), pedal=('Subbass 16', 'Octavebass 8', 'Choralbass 4', 'Posaune 16'),
                           swell_to_great=True, great_to_pedal=True, swell_box=1.0),
    # the continuo a little brighter: the Great's flutes 8' and 4' with the Swell's
    'continuo_bright': Registration(great=('Rohrflöte 8', 'Spitzflöte 4'), swell=('Gedackt 8', 'Flute 4'),
                                    pedal=('Subbass 16', 'Octavebass 8'), swell_to_great=True, swell_box=0.7),
    # a solo reed over flutes
    'reed': Registration(great=('Rohrflöte 8', 'Trumpet 8'), swell=('Gedackt 8', 'Flute 4'), pedal=('Subbass 16', 'Octavebass 8'),
                         swell_box=0.8),
}


def pipe(stop: Stop, midi: int, dur: float, seed: int, tremulant: bool = False) -> np.ndarray:
    """One pipe of a stop (every rank of a mixture) sounding for dur seconds, mono."""
    n = int((dur + RELEASE) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    spec = SPECTRA[stop.family]
    for rank, feet in enumerate(stop.feet):
        shift = footage_shift(feet)
        if stop.breaks:   # a mixture rank breaks back an octave each octave above middle C
            shift -= 12 * max(0, (midi - 60) // 12 + 1) if midi >= 60 else 0
        m = midi + shift
        if m > 108:
            m -= 12 * ((m - 108) // 12 + 1)
        rng = np.random.default_rng(np.random.SeedSequence([seed, zlib.crc32(stop.name.encode()), m, rank]))   # stable across runs, unlike hash()
        cents = rng.uniform(-DETUNE_CENTS, DETUNE_CENTS) + stop.detune_cents
        f0 = 440 * 2 ** ((m - 69 + cents / 100) / 12)
        phase = 2 * np.pi * f0 * t
        if tremulant:
            phase += 2 * np.pi * f0 * (2 ** (5 / 1200) - 1) / (2 * np.pi * 6.0) * np.sin(2 * np.pi * 6.0 * t)
        tilt = max(0.0, (m - 72) / 12) * 3   # treble pipes: fewer upper harmonics
        for h, db in enumerate(spec, start=1):
            if f0 * h > SR / 2 * 0.9:
                break
            out += 10 ** ((db - tilt * (h - 1)) / 20) * np.sin(h * phase + rng.uniform(0, 2 * np.pi))
        if stop.family in CHIFF:   # the breath as the pipe speaks, around its second harmonic
            k = int(0.03 * SR)
            burst = rng.standard_normal(k) * np.hanning(2 * k)[k:]
            lo, hi = min(f0 * 1.5, SR / 2 * 0.8), min(f0 * 3.5, SR / 2 * 0.95)
            if hi > lo * 1.05:
                burst = sosfilt(butter(2, [lo, hi], 'bandpass', fs=SR, output='sos'), burst)
                out[:k] += burst / max(np.abs(burst).max(), 1e-9) * 10 ** (CHIFF[stop.family] / 20)
    wind = sosfilt(butter(2, min(4000, SR / 2 * 0.9), 'lowpass', fs=SR, output='sos'),
                   np.random.default_rng(np.random.SeedSequence([seed, midi, 7])).standard_normal(n))
    out += wind * 10 ** (WIND_DB / 20)
    # how it speaks and stops: lower pipes speak a little slower
    attack = ATTACK[stop.family] * (1.0 + max(0, 60 - midi) / 36)
    env = np.ones(n)
    a = min(n, int(attack * SR))
    env[:a] = np.linspace(0, 1, a) ** 1.5
    r = int(RELEASE * SR)
    env[n - r:] *= np.linspace(1, 0, r)
    if tremulant:
        env *= 1 + 0.12 * np.sin(2 * np.pi * 6.0 * t)
    peak = np.abs(out).max() or 1
    return out / peak * env * 10 ** (stop.level_db / 20) / np.sqrt(len(stop.feet))


def swell_box(x: np.ndarray, opening: float) -> np.ndarray:
    """The Swell division through its shutters: quieter and darker as they close."""
    gain = 10 ** (-20 * (1 - opening) / 20)
    cutoff = 1500 * (10 ** (opening * np.log10(10000 / 1500)))
    return sosfilt(butter(2, min(cutoff, SR / 2 * 0.95), 'lowpass', fs=SR, output='sos'), x, axis=0) * gain


# Where each division stands in the case, (pan of its centre, how far its pipes
# fan out, seconds further back): the pedal in towers either side, the Great in
# the middle, the Swell behind it
CASE = {'pedal': (0.0, 0.85, 0.004), 'great': (0.0, 0.55, 0.0), 'swell': (0.0, 0.4, 0.006)}
EAR_DELAY = 0.0006     # seconds between the ears for a pipe at the far side


def case_position(midi: int, division: str) -> tuple[float, float]:
    """(pan, seconds of delay) for a pipe: the C side left, the C-sharp side
    right, fanning further out the further a pipe is from the middle of the
    keys (the big pipes at the outside, as cases are built)."""
    centre, fan, back = CASE[division]
    side = -1 if midi % 2 == 0 else 1
    spread = 0.35 + 0.65 * min(1.0, abs(midi - 60) / 30)
    return float(np.clip(centre + side * fan * spread, -1, 1)), back


def _place_pipe(x: np.ndarray, pan: float, back: float) -> np.ndarray:
    """A mono pipe placed: level by pan, and a fraction of a millisecond later at
    the far ear, so it sounds located rather than panned."""
    angle = (pan + 1) * np.pi / 4
    lag = int(abs(pan) * EAR_DELAY * SR)
    near, far = x * (np.cos(angle) if pan <= 0 else np.sin(angle)), x * (np.sin(angle) if pan <= 0 else np.cos(angle))
    far = np.concatenate([np.zeros(lag), far])[:len(x)]
    pre = int(back * SR)
    l, r = (near, far) if pan <= 0 else (far, near)
    out = np.zeros((len(x) + pre, 2))
    out[pre:, 0], out[pre:, 1] = l, r
    return out


def play(notes: list, reg: Registration, seed: int = 0, normalize: bool = True) -> np.ndarray:
    """Stereo organ sound for a list of accompany.Note (voice 'pedal' or a
    manual: 'great' / 'swell'), through the registration's couplers and box."""
    end = max(n.end for n in notes) + RELEASE + 0.2
    total = int(end * SR)
    buses = {d: np.zeros((total, 2)) for d in DIVISIONS}
    for note in notes:
        sounds = []   # (division, midi)
        if note.voice == 'pedal':
            sounds.append(('pedal', note.midi))
            if reg.great_to_pedal: sounds.append(('great', note.midi))
            if reg.swell_to_pedal: sounds.append(('swell', note.midi))
        else:
            manual = note.voice if note.voice in ('great', 'swell') else ('great' if reg.great else 'swell')
            sounds.append((manual, note.midi))
            if manual == 'great' and reg.swell_to_great: sounds.append(('swell', note.midi))
        extra = []
        for div, m in sounds:
            if div == 'swell' and reg.swell_octave: extra.append((div, m + 12))
            if div == 'swell' and reg.swell_suboctave: extra.append((div, m - 12))
        for div, m in sounds + extra:
            for name in getattr(reg, div):
                stop = DIVISIONS[div][name]
                x = pipe(stop, m, note.end - note.start, seed, reg.tremulant and div == 'swell') * note.velocity
                pan, back = case_position(m, div)
                y = _place_pipe(x, pan, back)
                i = int(note.start * SR)
                j = min(total, i + len(y))
                buses[div][i:j] += y[:j - i]
    buses['swell'] = swell_box(buses['swell'], reg.swell_box)
    out = sum(buses.values())
    return out / max(np.abs(out).max(), 1e-9) * 0.9 if normalize else out


def play_plan(notes: list, plan: dict, seed: int = 0) -> np.ndarray:
    """Notes played through more than one registration: each note's `reg` (its
    voice's suffix after ':', e.g. 'manual:chorale') names the registration it
    sounds with; changes happen between phrases, as an organist makes them."""
    groups = {}
    for n in notes:
        name = n.voice.split(':')[1] if ':' in n.voice else next(iter(plan))
        groups.setdefault(name, []).append(type(n)(n.start, n.end, n.midi, n.velocity, n.voice.split(':')[0]))
    outs = [play(ns, plan[name], seed, normalize=False) for name, ns in groups.items()]   # their own levels: a fuller registration is louder
    n = max(len(o) for o in outs)
    total = sum(np.pad(o, ((0, n - len(o)), (0, 0))) for o in outs)
    return total / max(np.abs(total).max(), 1e-9) * 0.9
