"""How well the accompanist plays (skill, 0..1: 1, the default, a fine
player; 0.6 a competent one). Applied to the notes an instrument's style
pass has made:

- Timing: at 0.6 and above, the human looseness the style passes already
  have, never tighter (a player is never a sequencer); below it, looser, with
  a tendency to rush or drag.
- Ornament: the style passes ask `chance()` for their trills, passing notes,
  broken chords and flourishes, so a skilled player ornaments more, and well.
- Mistakes, below MISTAKES_BELOW: a wrong note now and then, usually caught
  and corrected (the wrong key, then the right one a beat of a second later),
  sometimes left; a neighbouring key brushed with the right one for a moment.
- Fumbling, below FUMBLE_BELOW, growing toward 0: someone who can't really
  play it. Late into chords, sometimes very late; finding a chord's notes one
  at a time; timid, uneven touch; falling behind the choir and skipping a
  chord or two to catch up; notes dropped, whole chords missed, leaning on the
  bass; most notes wrong, corrected slowly, sometimes to another wrong one.
- A breakdown, below BREAKDOWN_BELOW: a stretch played on the wrong chords,
  an abrupt stop, a few tentative notes looking for the place, and back in at
  the next phrase. Below TWICE_BELOW it can happen twice.

With a choir, where it breaks down and where it gives up on a choir that's
fallen apart come from the plan it shares with the choir (ensemble.py).

All seeded: a bad performance is as reproducible as a good one.
"""
import numpy as np

DEFAULT = 1.0
COMPETENT = 0.6         # at and above this, the style passes' human timing as it is
MISTAKES_BELOW = 0.45
BREAKDOWN_BELOW = 0.15
TWICE_BELOW = 0.07
MAX_LOOSENESS = 5.0     # how much looser the timing gets at skill 0
FUMBLE_BELOW = 0.2


def looseness(skill: float) -> float:
    """A multiplier on timing spread: 1 for a competent player or better (never tighter)."""
    return 1.0 + (MAX_LOOSENESS - 1.0) * max(0.0, COMPETENT - skill) / COMPETENT


def chance(base: float, skill: float) -> float:
    """An ornament's chance at this skill: none at 0, base at a competent player, up to twice base at 1."""
    return float(np.clip(base * (skill / COMPETENT if skill <= COMPETENT else 1 + (skill - COMPETENT) / (1 - COMPETENT)), 0, 1))


def _note(n, **kw):
    return type(n)(**{**{'start': n.start, 'end': n.end, 'midi': n.midi, 'velocity': n.velocity, 'voice': n.voice}, **kw})


def loosen(notes: list, skill: float, rng) -> list:
    """Timing beyond a competent player's: each onset moved further, and a drift
    (rushing or dragging) that wanders over the piece."""
    extra = looseness(skill) - 1.0
    if extra <= 0:
        return notes
    out, drift = [], 0.0
    for n in sorted(notes, key=lambda n: n.start):
        drift = float(np.clip(drift + rng.normal(0, 0.004 * extra), -0.04 * extra, 0.04 * extra))
        d = drift + rng.normal(0, 0.012 * extra)
        out.append(_note(n, start=max(0.0, n.start + d), end=max(n.start + d + 0.05, n.end + d * 0.5)))
    return out


def mistakes(notes: list, skill: float, rng, scale: list[int]) -> list:
    """Wrong notes, corrected or not, and brushed neighbouring keys."""
    if skill >= MISTAKES_BELOW:
        return notes
    p = 0.2 * ((MISTAKES_BELOW - skill) / MISTAKES_BELOW) ** 1.5
    out = []
    for n in notes:
        if rng.random() >= p:
            out.append(n)
            continue
        kind = rng.choice(['corrected', 'brushed', 'left'], p=[0.55, 0.3, 0.15])
        wrong = n.midi + int(rng.choice([-2, -1, 1, 2]))
        if kind == 'corrected':   # the wrong key, then the right one
            fix = n.start + rng.uniform(0.08, 0.2)
            out.append(_note(n, end=min(n.end, fix), midi=wrong))
            if fix < n.end - 0.03:
                out.append(_note(n, start=fix))
        elif kind == 'brushed':   # the neighbouring key caught with the right one
            out.append(n)
            out.append(_note(n, end=n.start + rng.uniform(0.05, 0.15), midi=n.midi + int(rng.choice([-1, 1])), velocity=n.velocity * 0.7))
        else:
            out.append(_note(n, midi=wrong))
    return out


def fumble(notes: list, skill: float, rng, scale: list[int]) -> list:
    """A player who can't really manage the piece, all the way through (see above)."""
    if skill >= FUMBLE_BELOW:
        return notes
    s = (FUMBLE_BELOW - skill) / FUMBLE_BELOW            # 0 at the threshold .. 1 at skill 0
    chords = []                                            # notes grouped by when they were meant to start
    for n in sorted(notes, key=lambda n: n.start):
        if chords and n.start - chords[-1][0].start < 0.08:
            chords[-1].append(n)
        else:
            chords.append([n])
    out, lag = [], 0.0
    for chord in chords:
        if lag > 0.7 and rng.random() < 0.7:              # too far behind: skip ahead to catch up
            lag *= 0.3
            continue
        if rng.random() < 0.25 * s:                        # missed this one altogether
            lag += 0.1
            continue
        hesitation = rng.exponential(0.12 + 0.3 * s) if rng.random() < 0.6 * s + 0.2 else 0.0
        lag = float(np.clip(lag + hesitation * 0.6 - 0.05, 0.0, 1.5))   # falls behind, claws a little back
        bass = min(chord, key=lambda n: n.midi)
        kept = [n for n in chord if n is bass or rng.random() > 0.45 * s]
        t = chord[0].start + lag + hesitation
        for k, n in enumerate(sorted(kept, key=lambda n: n.midi)):   # finding the notes one at a time
            start = t + k * rng.uniform(0.04, 0.05 + 0.2 * s)
            vel = n.velocity * rng.uniform(0.45, 0.85)
            end = max(start + 0.08, n.end + lag)
            if rng.random() < 0.35 * s + 0.1:              # wrong, and slow to put right (sometimes wrong again)
                wrong = n.midi + int(rng.choice([-2, -1, 1, 2, 3]))
                fix = start + rng.uniform(0.2, 0.2 + 0.4 * s)
                out.append(_note(n, start=start, end=min(end, fix), midi=wrong, velocity=vel))
                if fix < end - 0.05:
                    right = n.midi if rng.random() > 0.3 * s else n.midi + int(rng.choice([-1, 1]))
                    out.append(_note(n, start=fix, end=end, midi=right, velocity=vel * 0.9))
            else:
                out.append(_note(n, start=start, end=end, velocity=vel))
    return out


def breakdown_spans(skill: float, rng, phrases: list[tuple[float, float]]) -> list[dict]:
    """Where the accompanist breaks down: a stretch of a phrase on the wrong
    chords, stopping there, and back in at the next phrase."""
    if skill >= BREAKDOWN_BELOW or len(phrases) < 3:
        return []
    count = 2 if skill < TWICE_BELOW and len(phrases) >= 5 else 1
    picks = sorted(rng.choice(np.arange(1, len(phrases) - 1), size=min(count, len(phrases) - 2), replace=False))
    out = []
    for k in picks:
        a, b = phrases[k]
        out.append({'kind': 'breakdown', 'a': a, 'b': b, 'stop': a + (b - a) * rng.uniform(0.4, 0.7),
                    'resume': phrases[k + 1][0], 'shift': int(rng.choice([-2, -1, 1, 2, 5]))})
    return out


def breakdowns(notes: list, spans: list[dict], rng) -> list:
    """Each breakdown: the right shape on the wrong chords, a stop, a few quiet
    notes looking for the place, and back in at the next phrase."""
    for sp in spans:
        a, b, stop, resume = sp['a'], sp['b'], sp['stop'], sp['resume']
        kept, tried = [], []
        for n in notes:
            if a <= n.start < stop:                 # the right shape on the wrong chords
                kept.append(_note(n, midi=n.midi + sp['shift']))
            elif stop <= n.start < resume:          # stopped
                continue
            else:
                kept.append(_note(n, end=min(n.end, stop) if n.start < stop < n.end else n.end))
        low = sorted(n.midi for n in notes if a <= n.start < b)[:1] or [48]
        t = stop + rng.uniform(0.4, 0.9)
        while t < resume - 0.3:                     # looking for the place: a few quiet, uncertain notes
            tried.append(type(notes[0])(t, t + rng.uniform(0.15, 0.4), int(low[0] + rng.choice([0, 2, 3, 5, 7, -2])),
                                        0.35, notes[0].voice))
            t += rng.uniform(0.35, 0.8)
        notes = kept + tried
    return notes


RALLY = 1.15   # how much harder the accompanist plays, carrying on alone to rally the choir


def given_up(notes: list, ev: dict) -> list:
    """The accompanist after the choir has fallen apart (ensemble.py): playing
    on harder to rally them (from rally to stop), stopping, then only its
    tries at leading them back in (each (from, to)), and back for good at
    `back` if the choir is coming back."""
    rally, stop, back, tries = ev['rally'], ev['stop'], ev.get('back'), ev.get('tries', [])
    out = []
    for n in notes:
        if n.start < stop:
            out.append(_note(n, end=min(n.end, stop + 0.15), velocity=min(1.0, n.velocity * RALLY) if n.start >= rally else n.velocity))
        elif back is not None and n.start >= back:
            out.append(n)
        else:
            for t0, t1 in tries:
                if t0 <= n.start < t1:
                    out.append(_note(n, end=min(n.end, t1 + 0.15)))
    return out


def perform(notes: list, skill: float, seed: int, scale: list[int], phrases: list[tuple[float, float]],
            events: list[dict] | None = None) -> list:
    """The notes as a player of this skill plays them. events (ensemble.py),
    when it plays with a choir: its breakdowns, and where it gives up on a
    choir that has fallen apart, instead of breaking down on its own."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 311]))
    notes = loosen(notes, skill, rng)
    notes = fumble(notes, skill, rng, scale) if skill < FUMBLE_BELOW else mistakes(notes, skill, rng, scale)
    if events is None:
        notes = breakdowns(notes, breakdown_spans(skill, rng, phrases), rng)
    else:
        notes = breakdowns(notes, [e for e in events if e['kind'] == 'breakdown'], rng)
        for e in events:
            if e['kind'] == 'give_up':
                notes = given_up(notes, e)
    return sorted(notes, key=lambda n: n.start)
