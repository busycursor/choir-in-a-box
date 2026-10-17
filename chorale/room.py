"""A sung render placed in a room: each singer panned to where they stand, at
their distance from the listener, into the room's reverb. The rooms are
synthesized: decorrelated pink noise per side with an exponential tail,
band-limited, early reflections and a pre-delay baked in, calibrated on pink
noise so wet_db means the same in every room. Equal-power pan; distance as
level, a little proximity bass up close and a duller top far off, and more
room further back.

The parts are balanced first: SoulX sings each voice at its own level (m2's
tenor came out well above the rest), so every part is brought to the same
loudness, a section measured as a whole, then set by BALANCE: in a chorale the
soprano has the tune, the bass is the foundation, and the inner voices carry
the harmony a little under them. Then the whole choir shapes each phrase
(parts.json's phrases, fermata to fermata): in a little under the level,
swelling toward the phrase's middle, easing into its cadence; the last phrase
a little softer.

Usage: python -m chorale.room <render dir> [--venue=church|large_church|larger_church] [--audience[=0.35]]
                               [--applause=applause|applause_hesitant|applause_finale] [--conductor[="his line"]]
Reads <render dir>/render.json and its stems; writes <render dir>/<room>.wav (stereo),
and with --audience <room>-live.wav: heard live (audience.py, from the picked takes),
the level from 0 (nobody) to 1 (a badly behaved audience). --conductor has him
introduce the piece first (conductor.py): the take picked for that line in
audience/picks.json, or a new one made with ElevenLabs (listen, then pick).
"""
import json, subprocess, sys, tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.signal import fftconvolve, sosfilt, butter

SR = 24000  # SoulX's rate


@dataclass(frozen=True)
class Room:
    decay: float      # seconds of tail
    highpass: int
    lowpass: int
    pre_ms: int
    early: str        # aecho delays|decays: early reflections
    wet_db: float     # reverb under the dry voice at the typical distance, by loudness


ROOMS = {
    'small_church': Room(decay=1.6, highpass=140, lowpass=6000, pre_ms=18, early='18|31|47:0.24|0.17|0.12', wet_db=-11),
    'church':       Room(decay=2.4, highpass=120, lowpass=5500, pre_ms=30, early='30|52|80:0.22|0.16|0.11', wet_db=-9),
    'large_church': Room(decay=3.2, highpass=100, lowpass=5000, pre_ms=42, early='42|74|110:0.2|0.15|0.1', wet_db=-7),
    'larger_church': Room(decay=3.8, highpass=90, lowpass=4800, pre_ms=52, early='52|90|134:0.2|0.15|0.1', wet_db=-6),
}
# A venue: a room and how many people fill it (1 the size the audience levels were set at)
VENUES = {'small_church': ('small_church', 0.6), 'church': ('church', 1.0), 'large_church': ('large_church', 1.0), 'larger_church': ('larger_church', 1.4)}

BALANCE = {'Soprano': 0.0, 'Alto': -2.5, 'Tenor': -3.0, 'Bass': -1.0}  # dB, after every part is level-matched
SWELL = (-1.5, 1.0, -2.5)   # dB at a phrase's start, its swell (PEAK_AT through it), its cadence
PEAK_AT = 0.55
LAST_PHRASE_DB = -1.0
TYPICAL_DISTANCE = 0.3
DISTANCE_LEVEL_DB = -5   # per unit of distance
DISTANCE_ROOM_DB = 8     # more room per unit of distance
PEAK = 10 ** (-1 / 20)   # the mix peaks at -1 dBFS
LUFS = -20               # ...or sits at this loudness, whichever is quieter


@dataclass(frozen=True)
class Seat:
    pan: float       # -1 left .. 1 right, as heard from the nave
    distance: float  # 0 close .. 1 at the back


def impulse(room: Room, seed: int = 7) -> np.ndarray:
    """The room's stereo impulse (frames, 2)."""
    d = f'{room.decay:.3f}'
    chain = ['[0:a][1:a]amerge=inputs=2', f'afade=t=out:st=0:d={d}:curve=exp',
             f'highpass=f={room.highpass}', f'lowpass=f={room.lowpass}', f'aecho=1:1:{room.early}']
    if room.pre_ms:
        chain.append(f'adelay={room.pre_ms}:all=1')
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'engine') as tmp:
        out = Path(tmp) / 'ir.wav'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', f'anoisesrc=d={d}:c=pink:r={SR}:a=0.5:s={seed}',
                        '-f', 'lavfi', '-i', f'anoisesrc=d={d}:c=pink:r={SR}:a=0.5:s={seed + 12}',
                        '-filter_complex', ','.join(chain), str(out)], check=True)
        ir, _ = sf.read(out)
    return ir


def loudness(x: np.ndarray) -> float:
    return pyloudnorm.Meter(SR).integrated_loudness(x if x.ndim == 2 else np.stack([x, x], 1))


def calibration(ir: np.ndarray) -> float:
    """dB the convolution changes loudness by, on pink noise."""
    rng = np.random.default_rng(3)
    white = rng.standard_normal(4 * SR)
    pink = np.fft.irfft(np.fft.rfft(white) / np.sqrt(np.maximum(np.arange(len(white) // 2 + 1), 1)), len(white))
    noise = np.stack([pink, pink], 1) * 0.2 / np.abs(pink).max()
    wet = np.stack([fftconvolve(noise[:, 0], ir[:, 0])[:len(noise)], fftconvolve(noise[:, 1], ir[:, 1])[:len(noise)]], 1)
    return loudness(noise) - loudness(wet)


def shelf(x: np.ndarray, freq: float, gain_db: float, high: bool) -> np.ndarray:
    """A gentle shelf: the band above (or below) freq raised or cut by gain_db."""
    if abs(gain_db) < 0.05:
        return x
    sos = butter(2, freq, 'highpass' if high else 'lowpass', fs=SR, output='sos')
    return x + (10 ** (gain_db / 20) - 1) * sosfilt(sos, x)


def place(stem: np.ndarray, seat: Seat) -> tuple[np.ndarray, float]:
    """A mono stem panned and set back: (stereo dry, its room send in dB)."""
    x = shelf(stem, 200, 2 - 4 * seat.distance, high=False)   # proximity bass close, less far
    x = shelf(x, 5000, -3 * seat.distance, high=True)          # a duller top far off
    x = x * 10 ** (DISTANCE_LEVEL_DB * (seat.distance - TYPICAL_DISTANCE) / 20)
    angle = (seat.pan + 1) * np.pi / 4
    return np.stack([np.cos(angle) * x, np.sin(angle) * x], 1), DISTANCE_ROOM_DB * (seat.distance - TYPICAL_DISTANCE)


def balanced(stems: list[tuple[np.ndarray, Seat, str]]) -> list[tuple[np.ndarray, Seat]]:
    """Every part at the same loudness (its singers summed), then set by BALANCE."""
    parts = {}
    for audio, _, part in stems:
        parts.setdefault(part, []).append(audio)
    gain = {}
    for part, takes in parts.items():
        n = max(len(t) for t in takes)
        together = sum(np.pad(t, (0, n - len(t))) for t in takes)
        gain[part] = 10 ** ((LUFS - loudness(together) + BALANCE.get(part, 0.0)) / 20)
    return [(audio * gain[part], seat) for audio, seat, part in stems]


def phrasing(n: int, phrases: list[list[float]], offset: float) -> np.ndarray:
    """A gain curve over n samples: each phrase (seconds, plus offset: where the
    render puts the score's 0) shaped by SWELL, smoothly between them."""
    if not phrases:
        return np.ones(n)
    times, dbs = [], []
    for k, (a, b) in enumerate(phrases):
        extra = LAST_PHRASE_DB if k == len(phrases) - 1 else 0.0
        for frac, db in zip((0.0, PEAK_AT, 1.0), SWELL):
            times.append(offset + a + frac * (b - a)); dbs.append(db + extra)
    t = np.arange(n) / SR
    curve = np.interp(t, times, dbs)                      # held flat before the first phrase and after the last
    width = int(0.15 * SR)                                # smoothed, so no corner is heard
    curve = np.convolve(np.pad(curve, width, mode='edge'), np.hanning(2 * width + 1) / np.hanning(2 * width + 1).sum(), 'same')[width:-width]
    return 10 ** (curve / 20)


def staggered(stems: list[tuple[np.ndarray, Seat, str]], rows: dict, offset: float) -> list[tuple[np.ndarray, Seat, str]]:
    """Each section's singers given their own breaths through long lines (breathing.py)."""
    from chorale import breathing
    by_part = {}
    for i, (_, _, part) in enumerate(stems):
        by_part.setdefault(part, []).append(i)
    out = list(stems)
    for part, idx in by_part.items():
        for k, gaps in zip(idx, breathing.plan(rows.get(part, []), len(idx), offset, seed=sum(map(ord, part)))):
            audio, seat, _ = stems[k]
            out[k] = (breathing.apply(audio, gaps, SR), seat, part)
    return out


def mix(stems: list[tuple[np.ndarray, Seat, str]], room: Room, phrases: list[list[float]] | None = None,
        offset: float = 0.0, rows: dict | None = None) -> np.ndarray:
    """Sections breathing in turn, every part balanced, the choir phrasing
    together, every singer at their seat, into the room; stereo, peaking at
    -1 dBFS at most."""
    ir = impulse(room)
    calib = calibration(ir)
    if rows:
        stems = staggered(stems, rows, offset)
    placed = balanced(stems)
    if phrases:
        shape = phrasing(max(len(s) for s, _ in placed), phrases, offset)
        placed = [(s * shape[:len(s)], seat) for s, seat in placed]
    n = max(len(s) for s, _ in placed) + len(ir)
    dry, send = np.zeros((n, 2)), np.zeros((n, 2))
    for stem, seat in placed:
        d, send_db = place(stem, seat)
        dry[:len(d)] += d
        send[:len(d)] += d * 10 ** (send_db / 20)
    gain = 10 ** ((room.wet_db + calib) / 20)
    wet = np.stack([fftconvolve(send[:, 0], ir[:, 0])[:n], fftconvolve(send[:, 1], ir[:, 1])[:n]], 1) * gain
    out = dry + wet
    level = min(PEAK / max(np.abs(out).max(), 1e-9), 10 ** ((LUFS - loudness(out)) / 20))
    out *= level
    end = len(out)
    while end > 0 and np.abs(out[end - 1]).max() < 1e-5:
        end -= 1
    return out[:end]


# Where the singers stand, as heard from the nave: the classic order, sopranos
# on the left through basses on the right, the men a row behind the women.
SECTIONS = {'Soprano': Seat(-0.5, 0.35), 'Alto': Seat(-0.17, 0.35), 'Tenor': Seat(0.17, 0.5), 'Bass': Seat(0.5, 0.5)}
SECTION_WIDTH = 0.28   # a section's singers spread across this much of the pan


def seats(part: str, count: int, order: list[str] | None = None) -> list[Seat]:
    """The seats of a section's singers: spread across its place, alternately a
    little nearer and further, as a section stands in two ragged rows. Parts
    other than SATB (a canon's six) stand evenly across the front, in order."""
    if part in SECTIONS:
        c = SECTIONS[part]
    else:
        order = order or [part]
        k = order.index(part)
        c = Seat(-0.6 + 1.2 * k / max(1, len(order) - 1), 0.42)
    if count == 1:
        return [c]
    return [Seat(c.pan + SECTION_WIDTH * (k / (count - 1) - 0.5), c.distance + (0.06 if k % 2 else -0.04)) for k in range(count)]


def stems_of(render_dir: Path) -> list[tuple[np.ndarray, Seat, str]]:
    """Each singer's stem from a render and their seat (a section's singers are
    <part>-<k>.wav, a soloist <part>.wav)."""
    info = json.loads((render_dir / 'render.json').read_text())
    out = []
    order = list(info['voices'])
    for part, names in info['voices'].items():
        files = [render_dir / f'{part.lower()}-{k + 1}.wav' for k in range(len(names))] if len(names) > 1 else [render_dir / f'{part.lower()}.wav']
        for f, seat in zip(files, seats(part, len(files), order)):
            audio, sr = sf.read(f)
            assert sr == SR, f
            out.append((audio, seat, part))
    return out


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
    d = Path(args[0])
    name, crowd = VENUES[opt.get('venue', opt.get('room', 'church'))]
    from chorale.sing_parts import LEAD_IN  # where the render puts the score's 0
    parts = json.loads((d / 'parts.json').read_text())
    out = mix(stems_of(d), ROOMS[name], parts.get('phrases'), LEAD_IN, parts['parts'])
    sf.write(d / f'{name}.wav', out.astype(np.float32), SR)
    print(d / f'{name}.wav', f'{len(out) / SR:.1f}s')
    if '--audience' in sys.argv or 'audience' in opt:
        from chorale import audience
        chosen = audience.picks()
        if not chosen:
            raise SystemExit(f'no audience takes kept yet in {audience.KEPT}')
        intro = None
        if '--conductor' in sys.argv or 'conductor' in opt:
            from chorale import conductor
            line = opt.get('conductor') or conductor.LINE
            intro = audience.conductor_take(line)
            if intro is None:
                intro = conductor.say(line, takes=1)[0]
                print(f'conductor: made {intro.name}; not picked yet, so listen and list it in '
                      f'{conductor.LINES / "picks.json"} (kept out of the repo)')
        live = audience.live(out, parts.get('phrases') or [], LEAD_IN, chosen, intro=intro,
                             liveliness=float(opt.get('audience', audience.LIVELY)), applause_kind=opt.get('applause', 'applause'),
                             room_name=name, crowd=crowd)
        sf.write(d / f'{name}-live.wav', live.astype(np.float32), SR)
        print(d / f'{name}-live.wav', f'{len(live) / SR:.1f}s')
