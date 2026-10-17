"""How well the accompanist plays (skill, 0..1; 0.6 a competent player, the
default). Applied to the notes an instrument's style pass has made:

- Timing: at 0.6 and above, the human looseness the style passes already
  have, never tighter (a player is never a sequencer); below it, looser, with
  a tendency to rush or drag.
- Ornament: the style passes ask `chance()` for their trills, passing notes,
  broken chords and flourishes, so a skilled player ornaments more, and well.
- Mistakes, below MISTAKES_BELOW: a wrong note now and then, usually caught
  and corrected (the wrong key, then the right one a beat of a second later),
  sometimes left; a neighbouring key brushed with the right one for a moment.
- A breakdown, below BREAKDOWN_BELOW: a stretch played on the wrong chords,
  an abrupt stop, a few tentative notes looking for the place, and back in at
  the next phrase. Below TWICE_BELOW it can happen twice.

All seeded: a bad performance is as reproducible as a good one.
"""
import numpy as np

DEFAULT = 0.6
COMPETENT = 0.6         # at and above this, the style passes' human timing as it is
MISTAKES_BELOW = 0.45
BREAKDOWN_BELOW = 0.15
TWICE_BELOW = 0.07
MAX_LOOSENESS = 5.0     # how much looser the timing gets at skill 0


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


def breakdowns(notes: list, skill: float, rng, phrases: list[tuple[float, float]]) -> list:
    """A stretch on the wrong chords, a stop, searching, and back in at the next phrase."""
    if skill >= BREAKDOWN_BELOW or len(phrases) < 3:
        return notes
    count = 2 if skill < TWICE_BELOW and len(phrases) >= 5 else 1
    picks = sorted(rng.choice(np.arange(1, len(phrases) - 1), size=min(count, len(phrases) - 2), replace=False))
    for k in picks:
        a, b = phrases[k]
        resume = phrases[k + 1][0]
        wrong_until = a + (b - a) * rng.uniform(0.4, 0.7)
        stop = wrong_until
        shift = int(rng.choice([-2, -1, 1, 2, 5]))
        kept, tried = [], []
        for n in notes:
            if a <= n.start < wrong_until:          # the right shape on the wrong chords
                kept.append(_note(n, midi=n.midi + shift))
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


def perform(notes: list, skill: float, seed: int, scale: list[int], phrases: list[tuple[float, float]]) -> list:
    """The notes as a player of this skill plays them."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 311]))
    notes = loosen(notes, skill, rng)
    notes = mistakes(notes, skill, rng, scale)
    notes = breakdowns(notes, skill, rng, phrases)
    return sorted(notes, key=lambda n: n.start)
