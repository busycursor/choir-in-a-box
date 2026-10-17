"""Realizing a continuo part: the chords above the bass, voiced the way the
thoroughbass treatises teach (C. P. E. Bach's Versuch, Heinichen,
Saint-Lambert).

1. The harmony. Where the score encodes figures, they say it. A chorale
   doesn't: there the figures are the choir itself, so the chord at each bass
   note is read from the voices, at the beat (offbeat passing notes in the
   voices don't make a new chord). A held bass under moving voices gets a new
   chord where the harmony changes (a 4-3 suspension resolving), not at every
   passing note.
2. The voicing. For each chord, every way of placing the right hand's notes
   (three, in the usual continuo texture) in its range is a candidate; a
   best-path search across the whole piece picks the sequence that moves least,
   never makes parallel fifths or octaves with the bass or between its own
   voices, keeps the right hand below the melody and its voices within an
   octave of each other, and doubles the right notes (the bass or the fifth,
   never the leading note or a seventh). Ties are broken by a seeded draw, so
   a realization is reproducible and a different seed is a different, equally
   correct one.
"""
from dataclasses import dataclass
import itertools

import numpy as np

RH_LOW, RH_HIGH = 52, 76     # E3..E5: where a continuo player's right hand sits
RH_VOICES = 3


@dataclass(frozen=True)
class Chord:
    start_q: float
    end_q: float
    bass: int                 # MIDI
    pcs: frozenset            # pitch classes sounding above the bass (bass's own included if doubled in the voices)
    melody: int | None        # the top voice's pitch here, which the right hand stays under
    cadence: bool = False     # a fermata or the end: thicker, broader


def _sounding(events: list, q: float):
    """The note a part is sounding at quarter q (or None)."""
    for off, beats, midi in events:
        if off - 1e-6 <= q < off + beats - 1e-6:
            return midi
    return None


def chords_from_voices(parts: dict, beat_q: float = 1.0) -> list[Chord]:
    """A chorale's chords, read from its voices at each bass note and at each
    beat where the harmony over a held bass changes."""
    ev = parts['events']
    sung = [p for p in parts.get('sung', ev) if p in ev]
    bass_name = sung[-1]
    top_name = sung[0]
    fermatas = set(round(q, 4) for q in parts.get('fermatas_q', []))
    end_q = max(off + beats for evs in ev.values() for off, beats, _ in evs)
    out = []
    for off, beats, bass in ev[bass_name]:
        # the beats inside this bass note, each a possible change of chord
        points = [off] + [b for b in np.arange(np.ceil(off / beat_q - 1e-6) * beat_q, off + beats - 1e-6, beat_q) if b > off + 1e-6]
        prev = None
        for i, q in enumerate(points):
            q_end = points[i + 1] if i + 1 < len(points) else off + beats
            pcs = frozenset(m % 12 for name in sung if (m := _sounding(ev[name], q)) is not None)
            if prev is not None and pcs == prev.pcs:
                out[-1] = Chord(prev.start_q, q_end, prev.bass, prev.pcs, prev.melody, prev.cadence)
                prev = out[-1]
                continue
            melody = _sounding(ev[top_name], q)
            cadence = round(q, 4) in fermatas or abs(q_end - end_q) < 1e-6
            prev = Chord(q, q_end, bass, pcs, melody, cadence)
            out.append(prev)
    return out


FIGURE_INTERVALS = {'': (3, 5), '5': (3, 5), '6': (3, 6), '64': (4, 6), '7': (3, 5, 7), '65': (3, 5, 6),
                    '43': (3, 4, 6), '42': (2, 4, 6), '2': (2, 4, 6), '9': (3, 5, 9), '4': (4, 5), '3': (3, 5)}


def chords_from_figures(bass_events: list, figures: list, key_pcs: list[int]) -> list[Chord]:
    """Chords from a figured bass: each figure read as intervals above the bass
    within the key (a bare bass note is a 5/3)."""
    figs = {round(q, 4): str(f).replace(' ', '').replace(',', '') for q, f in figures}
    out = []
    for off, beats, bass in bass_events:
        fig = figs.get(round(off, 4), '')
        digits = ''.join(ch for ch in fig if ch.isdigit())
        intervals = FIGURE_INTERVALS.get(digits, (3, 5))
        pcs = {bass % 12}
        for iv in intervals:
            pcs.add(_diatonic_above(bass, iv, key_pcs) % 12)
        sharp = '#' in fig or '+' in fig
        if sharp:  # an accidental on the figure: raise the third (the commonest case)
            third = _diatonic_above(bass, 3, key_pcs)
            pcs.discard(third % 12); pcs.add((third + 1) % 12)
        out.append(Chord(off, off + beats, bass, frozenset(pcs), None))
    return out


def _diatonic_above(bass: int, interval: int, key_pcs: list[int]) -> int:
    """The note a diatonic interval (3 = a third) above the bass, counting up the key's scale."""
    scale = sorted(key_pcs)
    i = min(range(len(scale)), key=lambda k: (bass % 12 - scale[k]) % 12)   # the bass's degree (or the one just below it)
    up = 0
    for step in range(interval - 1):
        up += (scale[(i + step + 1) % len(scale)] - scale[(i + step) % len(scale)]) % 12
    return bass + up


def candidates(ch: Chord, leading_pc: int | None, voices: int = RH_VOICES) -> list[tuple]:
    """Every right-hand voicing of a chord: `voices` notes, all of its pitch
    classes above the bass present, doubled by the rules."""
    above = sorted(ch.pcs - {ch.bass % 12}) or sorted(ch.pcs)
    seventh = (ch.bass + 10) % 12 in ch.pcs or (ch.bass + 11) % 12 in ch.pcs
    hi = min(RH_HIGH, ch.melody) if ch.melody is not None else RH_HIGH
    lo = max(RH_LOW, ch.bass + 3)
    pool = [m for m in range(lo, hi + 1) if m % 12 in ch.pcs]
    out = []
    for combo in itertools.combinations(pool, voices):
        got = {m % 12 for m in combo}
        if not set(above[:voices]) <= got:
            continue
        pcs = [m % 12 for m in combo]
        doubled = [pc for pc in set(pcs) if pcs.count(pc) > 1]
        if any(pc == leading_pc or (seventh and pc in ((ch.bass + 10) % 12, (ch.bass + 11) % 12)) for pc in doubled):
            continue   # never double the leading note or the seventh
        if combo[-1] - combo[0] > 12 + 7 or any(b - a > 12 for a, b in zip(combo, combo[1:])):
            continue   # the hand's span, and no voice more than an octave from the next
        out.append(combo)
    return out


def _parallel(a1: int, a2: int, b1: int, b2: int) -> bool:
    """Parallel fifths or octaves between two voices moving from a1/b1 to a2/b2."""
    if a1 == a2 and b1 == b2:
        return False
    i1, i2 = (a1 - b1) % 12, (a2 - b2) % 12
    same_way = (a2 - a1) * (b2 - b1) > 0
    return i1 == i2 and i1 in (0, 7) and same_way


def cost(prev: tuple | None, cur: tuple, prev_bass: int | None, bass: int, center: float = 64.0) -> float:
    c = abs(np.mean(cur) - center) * 0.15                       # stay in the middle of the hand's range
    if prev is None:
        return c
    moves = [abs(x - y) for x, y in zip(sorted(prev), sorted(cur))]
    c += sum(moves) + sum(4 for m in moves if m > 7)            # move little; no big leaps
    for x1, x2 in zip(sorted(prev), sorted(cur)):
        if prev_bass is not None and _parallel(x1, x2, prev_bass, bass):
            c += 100                                            # parallels with the bass
    for (x1, x2), (y1, y2) in itertools.combinations(list(zip(sorted(prev), sorted(cur))), 2):
        if _parallel(x1, x2, y1, y2):
            c += 100                                            # parallels inside the hand
    return c


def realize(chords: list[Chord], leading_pc: int | None, seed: int = 0, voices: int = RH_VOICES) -> list[tuple]:
    """The right hand's voicing for every chord: the best path through the
    candidates (seeded tie-breaks)."""
    rng = np.random.default_rng(seed)
    cands = [candidates(ch, leading_pc, voices) or candidates(ch, None, voices) or [tuple(sorted(
        min(range(RH_LOW, RH_HIGH + 1), key=lambda m: (m % 12 != pc, abs(m - 64))) for pc in list(ch.pcs)[:voices]))]
        for ch in chords]
    noise = [rng.uniform(0, 0.5, len(c)) for c in cands]
    best = [[cost(None, v, None, chords[0].bass) + noise[0][k] for k, v in enumerate(cands[0])]]
    back = [[-1] * len(cands[0])]
    for i in range(1, len(chords)):
        row, ptr = [], []
        for k, v in enumerate(cands[i]):
            scores = [best[i - 1][j] + cost(u, v, chords[i - 1].bass, chords[i].bass) for j, u in enumerate(cands[i - 1])]
            j = int(np.argmin(scores))
            row.append(scores[j] + noise[i][k]); ptr.append(j)
        best.append(row); back.append(ptr)
    k = int(np.argmin(best[-1]))
    path = []
    for i in range(len(chords) - 1, -1, -1):
        path.append(cands[i][k]); k = back[i][k]
    return path[::-1]


def key_info(parts: dict, score_key: str | None = None) -> tuple[list[int], int | None]:
    """The key's scale pitch classes and its leading note, from the score's key
    (or from the bass line's pitch classes, roughly, without one)."""
    from music21 import key as m21key
    if score_key:
        k = m21key.Key(score_key.split()[0].replace('-', 'b') if ' ' not in score_key else score_key.split()[0],
                       score_key.split()[1].lower() if ' ' in score_key else 'major')
    else:
        from music21 import stream, note
        s = stream.Stream([note.Note(m) for evs in parts['events'].values() for _, _, m in evs])
        k = s.analyze('key')
    scale = sorted({p.pitchClass for p in k.getScale('major' if k.mode == 'major' else 'minor').getPitches()})
    leading = (k.tonic.pitchClass - 1) % 12
    return scale, leading
