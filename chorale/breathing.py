"""Staggered breathing: a section breathes together at the phrase breaks, but
through a long line its singers take quiet breaths one at a time while the
others carry the sound. Each singer runs on their own air (AIR seconds of
singing, seeded per singer); when it runs out they breathe partway through
the next long note (never on a word's start), unless a neighbour or too much
of the section is already breathing. A part with one singer breathes only at
its rests, as written.

The gaps are applied to each singer's finished stem (room.py), as a fade out,
a short silence and a fade back in.
"""
import numpy as np

AIR = (5.0, 8.0)        # seconds of singing between a singer's breaths, drawn per breath
LONG_NOTE = 0.9         # seconds: a note this long has room for a breath inside it
INSIDE = (0.5, 0.75)    # ...taken this far through it
GAP, FADE_OUT, FADE_IN = 0.3, 0.04, 0.08
AT_ONCE = 1 / 3         # of a section, breathing at the same moment at most


def notes_in_time(rows: list, offset: float) -> list[tuple[float, float, bool]]:
    """(start, end, sung) of each row of a part (parts.json), in the render's seconds."""
    out, t = [], offset
    for midi, secs, *_ in rows:
        out.append((t, t + secs, midi is not None)); t += secs
    return out


def plan(rows: list, singers: int, offset: float, seed: int = 0) -> list[list[tuple[float, float]]]:
    """Each singer's breath gaps (start, end) in seconds, for a section of `singers` on one part."""
    if singers < 2:
        return [[] for _ in range(singers)]
    notes = notes_in_time(rows, offset)
    spots = [(a + (b - a) * INSIDE[0], a + (b - a) * INSIDE[1]) for a, b, sung in notes if sung and b - a >= LONG_NOTE]
    rng = [np.random.default_rng([seed, k]) for k in range(singers)]
    air = [rng[k].uniform(*AIR) for k in range(singers)]
    sung_since = [0.0] * singers
    gaps: list[list[tuple[float, float]]] = [[] for _ in range(singers)]
    limit = max(1, int(singers * AT_ONCE))
    # Walk the part in time: singing uses air; a rest is a breath for everyone
    events = sorted([(a, 'note', b, sung) for a, b, sung in notes])
    spot_i = 0
    for a, _, b, sung in events:
        if not sung:
            if b - a >= 0.2:
                sung_since = [0.0] * singers
            continue
        sung_since = [s + (b - a) for s in sung_since]
        while spot_i < len(spots) and spots[spot_i][1] <= b + 1e-9:
            lo, hi = spots[spot_i]; spot_i += 1
            # those out of air, longest first, staggered within the spot
            due = sorted((k for k in range(singers) if sung_since[k] >= air[k]), key=lambda k: -sung_since[k])
            taken = []
            for k in due:
                if len(taken) >= limit:
                    break
                if any(abs(k - j) <= 1 for j in taken):
                    continue  # never next to someone breathing
                start = lo + (hi - lo - GAP) * len(taken) / max(1, limit) if hi - lo > GAP else lo
                gaps[k].append((start, start + GAP))
                taken.append(k)
                sung_since[k] = 0.0
                air[k] = rng[k].uniform(*AIR)
    return gaps


def apply(audio: np.ndarray, gaps: list[tuple[float, float]], sr: int) -> np.ndarray:
    """The stem with a quiet breath at each gap: faded out, silent, faded back in."""
    if not gaps:
        return audio
    gain = np.ones(len(audio))
    fo, fi = int(FADE_OUT * sr), int(FADE_IN * sr)
    for a, b in gaps:
        i, j = int(a * sr), int(b * sr)
        if i - fo < 0 or j + fi > len(audio):
            continue
        gain[i - fo:i] = np.minimum(gain[i - fo:i], np.linspace(1, 0, fo))
        gain[i:j] = 0
        gain[j:j + fi] = np.minimum(gain[j:j + fi], np.linspace(0, 1, fi))
    return audio * gain
