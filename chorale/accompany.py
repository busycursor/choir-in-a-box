"""The accompaniment: what an organist, harpsichordist or pianist plays with
the choir, from the score. Notes are placed on the performed timeline, the
same tempo map the choir sang to (fermata holds and all) plus the render's
lead-in, so the instrument holds and moves with the singers.
"""
from dataclasses import dataclass

import numpy as np

from chorale.timing import TempoMap
from chorale.sing_parts import LEAD_IN


@dataclass(frozen=True)
class Note:
    start: float    # seconds into the render
    end: float
    midi: int
    velocity: float = 0.7   # 0..1
    voice: str = ''         # which hand or division plays it (instrument-specific)


def clock(parts: dict):
    """(start, end) in render seconds for a span of score quarters."""
    tm = TempoMap.from_json(parts['timing'])
    return lambda a, b: (LEAD_IN + tm.start(a), LEAD_IN + tm.end(b))


def score_notes(parts: dict, name: str) -> list[Note]:
    """A part's notes as written, on the performed timeline."""
    at = clock(parts)
    out = []
    for off, beats, midi in parts['events'][name]:
        a, b = at(off, off + beats)
        out.append(Note(a, b, int(midi)))
    return out


# How each instrument accompanies a chorale by default: the organ and the
# harpsichord realize the continuo; a piano plays the four parts, as a pianist
# accompanying a hymn does
STYLE = {'organ': 'continuo', 'harpsichord': 'continuo', 'piano': 'doubling'}
LIFT = 0.08          # seconds an organist lifts before a new phrase
ROLL = (0.012, 0.03)  # seconds between a rolled chord's notes (harpsichord), drawn per chord
ROLL_CADENCE = (0.05, 0.08)
RESTRIKE_Q = 2.0     # a harpsichord chord this many quarters long is struck again on the beat


def _jitter(rng, n: Note, secs: float) -> Note:
    d = rng.uniform(-secs, secs)
    return Note(max(0.0, n.start + d), n.end, n.midi, n.velocity, n.voice)


def continuo(parts: dict, instrument: str, seed: int = 0, score_key: str | None = None, voices: int = 3) -> list[Note]:
    """A realized continuo: the bass as written, the right hand's chords from
    realize.py, played the way the instrument is played."""
    from chorale import realize
    rng = np.random.default_rng(seed)
    at = clock(parts)
    sung = [p for p in parts.get('sung', parts['events']) if p in parts['events']]
    bass_part = next((n for n in parts['events'] if n not in sung), sung[-1])   # a continuo part if there is one
    scale, lead = realize.key_info(parts, score_key)
    if parts.get('figures'):
        chords = realize.chords_from_figures(parts['events'][bass_part], parts['figures'], scale)
    else:
        chords = realize.chords_from_voices(parts)
    voicings = realize.realize(chords, lead, seed=seed, voices=voices)
    out = []
    bass_voice = {'organ': 'pedal', 'harpsichord': 'lh', 'piano': 'lh'}[instrument]
    for off, beats, midi in parts['events'][bass_part]:
        a, b = at(off, off + beats)
        out.append(Note(a, b, int(midi), 0.7, bass_voice))
    held = {}   # organ: a note carried on through a chord that shares it
    for ch, voicing in zip(chords, voicings):
        a, b = at(ch.start_q, ch.end_q)
        if instrument == 'organ':
            for m in voicing:
                if m in held and abs(held[m].end - a) < 0.02:
                    held[m] = Note(held[m].start, b, m, held[m].velocity, held[m].voice)   # tied over
                else:
                    if m in held: out.append(held.pop(m))
                    held[m] = Note(a, b, m, 0.7, 'manual')
            for m in [m for m in held if m not in voicing]:
                out.append(held.pop(m))
    if instrument == 'harpsichord':
        out += harpsichord_figuration(chords, voicings, at, rng, scale)
    out += list(held.values())
    if instrument == 'organ':   # a small lift before each new phrase, the way an organist breathes with the choir
        ends = [at(0, q)[1] for q in parts.get('fermatas_q', [])]
        out = [Note(n.start, n.end - LIFT if any(abs(n.end - e) < 0.6 and n.end < max(x.end for x in out) - 0.05 for e in ends) else n.end,
                    n.midi, n.velocity, n.voice) for n in out]
    return out


# The harpsichordist's figuration, chosen chord by chord (seeded): how the
# continuo treatises describe a player filling out the harmony rather than
# striking block chords
BROKEN = 0.5          # of long chords, the share broken into a figure across the beat
ACCIACCATURA = 0.15   # of short chords, the share struck with a crushed dissonance
PASSING = 0.5         # of leaps of a third in the top voice, the share filled with a passing note
TRILL_NOTE = 0.075    # seconds per note of a cadential trill


def _step(m: int, scale: list[int], up: bool) -> int:
    """The scale note next above (or below) m."""
    k = m + (1 if up else -1)
    while k % 12 not in scale:
        k += 1 if up else -1
    return k


def harpsichord_figuration(chords, voicings, at, rng, scale) -> list[Note]:
    out = []

    def strike(t0, t1, ns, vel, roll):
        step = rng.uniform(*roll)
        for k, m in enumerate(sorted(ns)):
            out.append(Note(t0 + k * step, t1, int(m), vel, 'rh'))

    for i, (ch, voicing) in enumerate(zip(chords, voicings)):
        a, b = at(ch.start_q, ch.end_q)
        q = ch.end_q - ch.start_q
        notes = sorted(voicing)
        nxt = chords[i + 1] if i + 1 < len(chords) else None
        if ch.cadence:   # broad: rolled slowly, filled out, the bass doubled below
            fuller = notes + ([notes[-1] + 12 - (notes[-1] + 12 - ch.bass) % 12] if notes[-1] + 12 <= 79 else [])
            strike(a, b, fuller, 0.8, ROLL_CADENCE)
            if ch.bass - 12 >= 28:
                out.append(Note(a, b, ch.bass - 12, 0.7, 'lh'))
            continue
        if nxt is not None and nxt.cadence:   # a trill on the top note into the cadence, from the note above
            top, upper = notes[-1], _step(notes[-1], scale, True)
            strike(a, b, notes[:-1], 0.7, ROLL)
            t, k = a, 0
            while t < a + 0.75 * (b - a) - TRILL_NOTE:
                out.append(Note(t, t + TRILL_NOTE, upper if k % 2 == 0 else top, 0.6, 'rh')); t += TRILL_NOTE; k += 1
            out.append(Note(t, b, top, 0.65, 'rh'))
            continue
        if q >= RESTRIKE_Q and rng.random() < BROKEN:   # broken up and back across the chord, in eighths
            figure = notes + notes[-2:0:-1]
            eighths = int(q * 2)
            for k in range(eighths):
                t0, _ = at(ch.start_q + k * 0.5, ch.start_q + k * 0.5)
                out.append(Note(t0, b, figure[k % len(figure)], 0.7 if k == 0 else 0.6, 'rh'))
        elif q >= RESTRIKE_Q:
            for k in range(int(q)):
                t0, t1 = at(ch.start_q + k, min(ch.end_q, ch.start_q + k + 1))
                strike(t0, t1 if k + 1 < int(q) else b, notes if k == 0 else notes[1:], 0.75 if k == 0 else 0.6, ROLL)
        else:
            strike(a, b, notes, 0.75, ROLL)
            if rng.random() < ACCIACCATURA:   # a dissonance a step below the middle note, crushed in and let go
                crush = notes[len(notes) // 2] - 1
                if crush % 12 not in ch.pcs:
                    out.append(Note(a + 0.004, a + 0.06, crush, 0.55, 'rh'))
        if nxt is not None and q >= 1 and rng.random() < PASSING:   # fill a third in the top voice with a passing note
            nxt_top = max(voicings[i + 1])
            if abs(nxt_top - notes[-1]) in (3, 4):
                mid = _step(notes[-1], scale, nxt_top > notes[-1])
                if min(mid, nxt_top) < max(mid, nxt_top) and mid != nxt_top:
                    t0, _ = at(ch.end_q - 0.5, ch.end_q - 0.5)
                    out.append(Note(t0, b, mid, 0.55, 'rh'))
    return out


# The pianist: each phrase swells toward its middle and eases into its cadence,
# the tune voiced over the inner parts and a touch ahead of them
PHRASE_SWELL = 0.3     # velocity added at a phrase's peak
MELODY_LEAD = 0.008    # seconds the tune is ahead of the chord
TOUCH = 0.04           # random variation of each note's velocity


def doubling(parts: dict, seed: int = 0) -> list[Note]:
    """The four parts as written, the way a pianist accompanies a hymn: phrases
    shaped, the tune a little forward, cadences rolled, the pedal holding each
    harmony until the next."""
    rng = np.random.default_rng(seed)
    sung = [p for p in parts.get('sung', parts['events']) if p in parts['events']]
    bass_onsets = sorted({n.start for n in score_notes(parts, sung[-1])})
    phrases = [(LEAD_IN + a, LEAD_IN + b) for a, b in parts.get('phrases', [])] or [(0.0, 1e9)]
    fermata_starts = {round(at_q, 3) for at_q in (clock(parts)(q, q)[0] for q in parts.get('fermatas_q', []))}
    last_end = max(n.end for name in sung for n in score_notes(parts, name))

    def shape(t):
        for k, (a, b) in enumerate(phrases):
            if a - 0.05 <= t <= b + 0.05:
                pos = (t - a) / max(b - a, 0.1)
                return 0.75 + PHRASE_SWELL * np.sin(np.pi * min(pos / 0.8, 1.0)) - (0.06 if k == len(phrases) - 1 else 0)
        return 0.75

    out = []
    for i, name in enumerate(sung):
        base = 0.8 if i == 0 else (0.7 if i == len(sung) - 1 else 0.58)
        for n in score_notes(parts, name):
            nxt = next((t for t in bass_onsets if t > n.start + 1e-3), n.end)
            vel = float(np.clip(base * shape(n.start) + rng.uniform(-TOUCH, TOUCH), 0.2, 0.98))
            start = n.start - (MELODY_LEAD if i == 0 else 0)
            if round(n.start, 3) in fermata_starts:   # a rolled cadence chord, bass first
                start += (len(sung) - 1 - i) * 0.03
            out.append(Note(max(0.0, start), max(n.end, nxt), n.midi, vel, name.lower()))
            if i == len(sung) - 1 and abs(n.end - last_end) < 0.01 and n.midi - 12 >= 24:   # the last bass doubled an octave down
                out.append(Note(n.start, n.end, n.midi - 12, vel, name.lower()))
    return out


def sections(parts: dict) -> list[int]:
    """Each phrase's section, the way an organist hears the form: a phrase whose
    tune repeats an earlier one starts the repeat (a chorale's first lines come
    back with new words), and what follows the repeat is the last section."""
    sung = [p for p in parts.get('sung', parts['events']) if p in parts['events']]
    ends = list(parts.get('fermatas_q', [])) or [max(o + b for o, b, _ in parts['events'][sung[0]])]
    tunes, start = [], 0.0
    for e in ends:
        tunes.append(tuple(m for o, b, m in parts['events'][sung[0]] if start - 1e-6 <= o <= e + 1e-6))
        start = e + 1e-6
    section, out, repeat_of = 0, [], None
    for k, tune in enumerate(tunes):
        first = tunes.index(tune)
        if first < k and repeat_of is None:      # the repeat begins
            section, repeat_of = 1, first
        elif repeat_of is not None and section == 1 and (first == k):   # past the repeat: the last section
            section = 2
        out.append(section)
    return out


ORGAN_PLANS = [   # registrations by section: the first statement, the repeat, the rest
    ('continuo', 'continuo_bright', 'chorale'),
    ('continuo', 'chorale', 'chorale'),
    ('continuo_bright', 'continuo', 'chorale'),
]
FULL_VOICES = 4   # the right hand in the fullest section
CHORD_TIMING = (0.008, 0.012)   # seconds: an organist's chord lands a little after the beat on average, never exactly
NOTE_SPREAD = 0.006             # ...and its notes not quite together
DETACH = (0.06, 0.12)           # a repeated bass note is lifted this much before it's struck again


def organ_plan(parts: dict, seed: int = 0) -> tuple[list[str], list[int]]:
    """Each phrase's registration and right-hand voice count, seeded."""
    rng = np.random.default_rng(seed)
    secs = sections(parts)
    plan = ORGAN_PLANS[rng.integers(len(ORGAN_PLANS))]
    return [plan[min(s, 2)] for s in secs], [FULL_VOICES if s == 2 else 3 for s in secs]


def humanized(notes: list[Note], seed: int) -> list[Note]:
    """An organist, not a sequencer: each chord a little off the beat, its notes
    not quite together, repeated bass notes detached, releases varying."""
    rng = np.random.default_rng(seed)
    out, chord_shift = [], {}
    for n in sorted(notes, key=lambda n: (n.start, n.midi)):
        key = round(n.start, 3)
        if key not in chord_shift:
            chord_shift[key] = float(np.clip(rng.normal(*CHORD_TIMING), -0.02, 0.03))
        d = chord_shift[key] + rng.uniform(-NOTE_SPREAD, NOTE_SPREAD)
        out.append(Note(max(0.0, n.start + d), max(n.start + d + 0.05, n.end - rng.uniform(0, 0.03)), n.midi, n.velocity, n.voice))
    bass = sorted((n for n in out if n.voice.startswith('pedal')), key=lambda n: n.start)
    for a, b in zip(bass, bass[1:]):
        if a.midi == b.midi and b.start - a.end < 0.05:
            out[out.index(a)] = Note(a.start, max(a.start + 0.05, b.start - rng.uniform(*DETACH)), a.midi, a.velocity, a.voice)
    return out


def organ_notes(parts: dict, seed: int = 0, score_key: str | None = None) -> list[Note]:
    """The organ continuo through its registration plan: each note's voice says
    which registration it sounds with ('manual:chorale')."""
    regs, voices = organ_plan(parts, seed)
    ends = [LEAD_IN + TempoMap.from_json(parts['timing']).end(q) for q in parts.get('fermatas_q', [])] or [1e9]
    phrase_of = lambda t: next((k for k, e in enumerate(ends) if t < e - 0.05), len(ends) - 1)
    three = continuo(parts, 'organ', seed, score_key)
    four = continuo(parts, 'organ', seed, score_key, voices=FULL_VOICES) if FULL_VOICES in voices else three
    out = []
    for src, want in ((three, 3), (four, FULL_VOICES)):
        for n in src:
            k = phrase_of(n.start)
            if voices[k] == want or (n.voice == 'pedal' and want == 3):
                out.append(Note(n.start, n.end, n.midi, n.velocity, f'{n.voice}:{regs[k]}'))
    return humanized(out, seed)


def notes_for(parts: dict, instrument: str, style: str | None = None, seed: int = 0, score_key: str | None = None) -> list[Note]:
    style = style or STYLE[instrument]
    if instrument == 'organ' and style == 'continuo':
        return organ_notes(parts, seed, score_key)
    if instrument == 'organ':   # doubling on the organ: manual for the upper parts, pedal for the bass
        sung = [p for p in parts.get('sung', parts['events']) if p in parts['events']]
        return humanized([Note(n.start, n.end, n.midi, n.velocity, ('pedal' if n.voice == sung[-1].lower() else 'manual') + ':chorale')
                          for n in doubling(parts, seed)], seed)
    return continuo(parts, instrument, seed, score_key) if style == 'continuo' else doubling(parts, seed)


# Where each instrument stands and how loud it sits: (pan, distance), dB under
# the choir, dB more into the room. The organ is up in the gallery and fills
# the building; the harpsichord and piano are down by the basses with the
# continuo. Levels set by ear: the organ at 6 dB under, so its fuller
# registrations stand out from its quiet ones.
PLACE = {'organ': ((0.0, 0.9), -6.0, 5.0), 'harpsichord': ((0.3, 0.35), -7.0, 0.0), 'piano': ((0.35, 0.4), -6.0, 0.0)}


def render(parts: dict, instrument: str, style: str | None = None, registration: str | None = None,
           seed: int = 0, score_key: str | None = None):
    """The accompaniment's sound and where it goes: (stereo, room.Seat, dB under the choir, dB more into the room)."""
    from chorale import organ, room, sampler
    notes = notes_for(parts, instrument, style, seed, score_key)
    if instrument == 'organ':
        if registration:   # one registration throughout
            notes = [Note(n.start, n.end, n.midi, n.velocity, n.voice.split(':')[0] + ':' + registration) for n in notes]
        sound = organ.play_plan(notes, organ.REGISTRATIONS, seed)
    else:
        sound = sampler.play(notes, instrument, seed)
    (pan, distance), under, fills = PLACE[instrument]
    return sound, room.Seat(pan, distance), under, fills
