"""How well the choir sings (choir skill, 0..1: 1, the default, a fine choir;
0.6 a competent one; the same curve as the accompanist's, skill.py). Every
fault is sung by SoulX, none put on afterwards: sing_parts.py changes what
each singer is asked to sing, and below COMPETENT sings each singer twice, a
first take for its natural pitch curve, then that curve with the faults drawn
in, sung again in melody mode.

- Pitchiness, below COMPETENT: a slow wander around the note, scoops up into
  notes, vibrato calmed on some notes, and the choir sagging flat phrase by
  phrase.
- Wrong notes in the obvious places, below WRONG_BELOW: a leap overshot or
  fallen short of, an accidental sung as the plain scale note, the top of a
  phrase landed a semitone short; some heard, and slid onto the right note.
- Unsure notes, below WRONG_BELOW: a note started off its pitch and hunted
  for (some never found), a note missed by a lot. None faster than a singer
  moves.
- Mispronunciation, below WRONG_BELOW: vowels slid into their neighbours,
  final consonants swallowed, consonants softened or swapped.
- Entries, below WRONG_BELOW: a cue missed (in late on a later note, or not at
  all) or jumped (in early).
- Losing the place, below LOST_BELOW: a singer a beat or two behind for a
  phrase, its end dropped to catch up at the next.
- Collapse, below COLLAPSE_BELOW: partway into a phrase every part gives up
  after the note it's on, until one part bravely finds the next entrance and
  the rest join, one by one. Below TWICE_BELOW it can happen twice. Below
  UNRECOVERABLE_BELOW (skill 0, near enough) it falls apart for good,
  somewhere 40-60% of the way through: a brave try or two at a later entrance
  comes to nothing, and the piece ends there. Where, and how the accompanist
  takes it, is ensemble.py's plan.

Each singer errs on their own (seeded per singer), so a section covers its
members' slips the way a real one does; all of it seeded and reproducible.
"""
import json
import zlib
from pathlib import Path

import numpy as np

DEFAULT = 1.0
COMPETENT = 0.6
WRONG_BELOW = 0.45
LOST_BELOW = 0.2
COLLAPSE_BELOW = 0.15
TWICE_BELOW = 0.07
UNRECOVERABLE_BELOW = 0.02
FALLS_APART = (0.4, 0.6)    # how far through the piece (by time) it falls apart for good: not so soon the joke is over too fast
SAG_CENTS = 45        # how flat the choir has sunk by the last phrase, at skill 0
WANDER_CENTS = 25     # pitch wandering around the note, at skill 0 (its spread)
MISS_SEMITONES = (2.0, 5.0)   # a note missed by a lot: this far off, up or down
FALTER_CENTS = (120, 300)    # where a hunted-for note starts, from its pitch
GLIDE = 1800                 # the fastest a singer's pitch moves, cents a second: no fault moves faster
SCOOP_CENTS = 80      # how far below a note a scoop starts, at skill 0

# ARPAbet neighbours a careless singer slides into
VOWEL_SLIP = {'IY': 'IH', 'IH': 'EH', 'EH': 'AE', 'EY': 'EH', 'AA': 'AH', 'AO': 'AA', 'OW': 'AO', 'UW': 'UH', 'UH': 'AH',
              'AE': 'EH', 'AH': 'AA', 'AY': 'AA', 'AW': 'AA', 'OY': 'OW', 'ER': 'AH'}
CONSONANT_SLIP = {'S': 'SH', 'SH': 'S', 'T': 'D', 'D': 'T', 'K': 'G', 'G': 'K', 'F': 'V', 'V': 'F', 'N': 'M', 'M': 'N', 'R': 'L'}


def severity(skill: float, below: float) -> float:
    """0 at `below` and above .. 1 at skill 0."""
    return max(0.0, below - skill) / below


def singer_seed(seed: int, name: str) -> int:
    return seed * 7919 + zlib.crc32(name.encode())


def scale_of(parts: dict) -> list[int]:
    """The piece's seven commonest pitch classes, by time sung: its scale, near enough."""
    weight = np.zeros(12)
    for rows in parts.values():
        for row in rows:
            if row[0] is not None:
                weight[int(row[0]) % 12] += row[1]
    return sorted(int(p) for p in np.argsort(weight)[-7:])


# --- sung: a singer's phrases (SoulX targets) changed before they're sung ---

def _slip(ph: str, rng, s: float) -> str:
    """A syllable's sounds as a careless singer makes them."""
    if not ph.startswith('en_'):
        return ph
    sounds = ph[3:].split('-')
    out = []
    for k, p in enumerate(sounds):
        base, stress = (p[:-1], p[-1]) if p[-1:].isdigit() else (p, '')
        if stress and base in VOWEL_SLIP and rng.random() < 0.4 + 0.3 * s:
            out.append(VOWEL_SLIP[base] + stress)
        elif not stress and k == len(sounds) - 1 and k > 0 and rng.random() < 0.3 + 0.4 * s:
            continue                                            # the final consonant swallowed
        elif not stress and base in CONSONANT_SLIP and rng.random() < 0.25:
            out.append(CONSONANT_SLIP[base])
        else:
            out.append(p)
    return 'en_' + '-'.join(out) if out else ph


def mangle(segments: list[dict], skill: float, seed: int, scale: list[int]) -> list[dict]:
    """A singer's phrases with the wrong notes and the slips of diction this skill makes."""
    s = severity(skill, WRONG_BELOW)
    if s <= 0:
        return segments
    rng = np.random.default_rng(np.random.SeedSequence([seed, 9013]))
    out = []
    for seg in segments:
        pitches = [int(x) for x in seg['note_pitch'].split()]
        phones = seg['phoneme'].split()
        types = [int(x) for x in seg['note_type'].split()]
        sung = sorted(p for p in pitches if p)
        top = sung[-1] if len(sung) > 3 else None
        prev, slipped = None, {}
        for k, (p, kind) in enumerate(zip(pitches, types)):
            if not p:
                continue
            leap = prev is not None and abs(p - prev) >= 5
            if rng.random() < 0.5 * s:
                if leap:                                        # overshot, or fell short of, the leap
                    pitches[k] = p + int(np.sign(p - prev)) * int(rng.choice([1, -1, -2], p=[0.35, 0.45, 0.2]))
                elif p % 12 not in scale:                       # the accidental sung as the plain note
                    pitches[k] = p + (-1 if (p - 1) % 12 in scale else 1)
                elif p == top:                                  # the top note a semitone short
                    pitches[k] = p - 1
            if kind == 2 and phones[k] not in slipped and rng.random() < 0.1 + 0.4 * s:
                slipped[phones[k]] = _slip(phones[k], rng, s)
            prev = p
        out.append({**seg, 'note_pitch': ' '.join(str(p) for p in pitches), 'written': seg['note_pitch'],
                    'phoneme': ' '.join(slipped.get(ph, ph) for ph in phones)})
    return out


# --- timing: a singer's phrases moved, cut and dropped before they're sung ---

RUN_UP = 0.4    # a phrase's silent lead-in (sing_parts.RUN_UP): a late entry gets its own
TAIL = 0.15     # and its padding after the last note (sing_parts.PAD)
FRAME = 0.02    # SoulX's pitch-curve frame (hop 480 at 24 kHz)


def _number(seg: dict) -> int:
    """The phrase's number in the part, from 1 (as the score has it, whatever's been dropped)."""
    return int(seg['index'].split('_')[-1]) + 1


def _rows(seg: dict) -> list[dict]:
    keys = ('duration', 'text', 'phoneme', 'note_pitch', 'note_type')
    cols = [seg[k].split() for k in keys] + [seg.get('written', seg['note_pitch']).split()]
    out, t = [], seg['time'][0] / 1000
    for d, text, ph, p, kind, w in zip(*cols):
        out.append({'at': t, 'secs': float(d), 'text': text, 'ph': ph, 'pitch': int(p), 'kind': int(kind), 'written': int(w)})
        t += float(d)
    return out


def _build(seg: dict, rows: list[dict]) -> dict:
    """A phrase from its rows (each with its own time): silent rows round its notes, content where the notes are."""
    notes = [r for r in rows if r['pitch']]
    first, last = notes[0], notes[-1]
    begin = max(0.0, first['at'] - RUN_UP)
    body = [{'secs': first['at'] - begin, 'text': '<SP>', 'ph': '<SP>', 'pitch': 0, 'kind': 1, 'written': 0}]
    for r in rows[rows.index(first):rows.index(last) + 1]:
        body.append(r)
    body.append({'secs': TAIL, 'text': '<SP>', 'ph': '<SP>', 'pitch': 0, 'kind': 1, 'written': 0})
    body[1] = {**body[1], 'kind': 2 if body[1]['kind'] == 3 else body[1]['kind']}   # a phrase can't open mid-word
    total = sum(r['secs'] for r in body)
    out = {k: v for k, v in seg.items() if k not in ('ghost', 'f0')}
    out.update({'time': [int(round(begin * 1000)), int(round((begin + total) * 1000))],
                'content': [int(round(first['at'] * 1000)), int(round((last['at'] + last['secs']) * 1000))],
                'duration': ' '.join(f'{r["secs"]:.3f}' for r in body), 'text': ' '.join(r['text'] for r in body),
                'phoneme': ' '.join(r['ph'] for r in body), 'note_pitch': ' '.join(str(r['pitch']) for r in body),
                'note_type': ' '.join(str(r['kind']) for r in body), 'written': ' '.join(str(r['written']) for r in body)})
    return out


def _sung(seg: dict) -> list[dict]:
    """The rows a singer really sings (not a ghost running start)."""
    rows = _rows(seg)
    if seg.get('ghost'):
        k = next(i for i, r in enumerate(rows) if r['pitch'])
        rows = rows[:k] + rows[k + 1:]
    return rows


CONSONANTS = 0.15   # how early a note can start for its consonants (sing_parts.MAX_LEAD, and a little)


def start_at(seg: dict, t: float) -> dict | None:
    """The phrase taken up from its first note at or after t (a late entry);
    a note starting just before t for its consonants counts as at t."""
    rows = _sung(seg)
    notes = [r for r in rows if r['pitch'] and r['at'] >= t - CONSONANTS]
    return _build(seg, rows[rows.index(notes[0]):]) if notes else None


def end_at(seg: dict, t: float, trim: bool = False) -> dict | None:
    """The phrase given up after the note sounding at t (finished, then
    nothing), or with trim, that note cut short at t."""
    rows = _sung(seg)
    notes = [r for r in rows if r['pitch'] and r['at'] < t - (0.1 if trim else 0)]
    if not notes:
        return None
    rows = rows[:rows.index(notes[-1]) + 1]
    if trim:
        rows[-1] = {**rows[-1], 'secs': min(rows[-1]['secs'], t - rows[-1]['at'])}
    return _build(seg, rows)


def shifted(seg: dict, secs: float) -> dict:
    rows = [{**r, 'at': r['at'] + secs} for r in _sung(seg)]
    return _build(seg, rows)


def entries(segments: list[dict], skill: float, rng, beat: float, log: list) -> list[dict]:
    """Cues missed or jumped, and (lower) the place lost for a phrase."""
    s = severity(skill, WRONG_BELOW)
    lost = severity(skill, LOST_BELOW)
    if s <= 0:
        return segments
    out = []
    for k, seg in enumerate(segments):
        a = seg['content'][0] / 1000
        nxt = segments[k + 1]['content'][0] / 1000 if k + 1 < len(segments) else None
        roll = rng.random()
        if k and roll < 0.05 * s:                                           # missed the cue altogether: sits the phrase out
            log.append(f'phrase {_number(seg)}: missed the cue, sat it out')
            continue
        if roll < 0.2 * s:                                                  # missed it, and came in a beat or so late
            late = start_at(seg, a + rng.uniform(0.7, 1.6) * beat)
            if late is not None:
                log.append(f'phrase {_number(seg)}: missed the cue, in {late["content"][0] / 1000 - a:.1f}s late')
                out.append(late)
            continue
        if roll < 0.28 * s and a > beat:                                    # jumped it: the phrase a little early
            lead = rng.uniform(0.2, 0.4) * beat
            log.append(f'phrase {_number(seg)}: jumped the cue, {lead:.2f}s early')
            out.append(shifted(seg, -lead))
            continue
        if lost and rng.random() < 0.35 * lost:                             # lost the place: behind, then skips to the next phrase
            lag = float(rng.choice([1, 1, 2])) * beat
            behind = shifted(seg, lag)
            if nxt is not None:
                behind = end_at(behind, nxt - 0.3, trim=True)
            if behind is not None:
                log.append(f'phrase {_number(seg)}: lost the place, {lag:.1f}s behind' + (', its end dropped to catch up' if nxt else ''))
                out.append(behind)
            continue
        out.append(seg)
    return out


def collapses(phrases: list[tuple[float, float]], skill: float, seed: int, parts: list[str]) -> list[dict]:
    """Where the whole choir falls apart (in render seconds), and which part
    finds the way back first; at the very lowest, the last one is for good."""
    if skill >= COLLAPSE_BELOW or len(phrases) < 3:
        return []
    rng = np.random.default_rng(np.random.SeedSequence([seed, 77]))
    out, last = [], len(phrases) - 1
    if skill < UNRECOVERABLE_BELOW:
        begin, end = phrases[0][0], phrases[-1][1]
        fall = begin + (end - begin) * rng.uniform(*FALLS_APART)
        out.append({'fall': fall, 'final': True, 'cues': [a for a, _ in phrases if a > fall],
                    'order': [str(p) for p in rng.permutation(parts)]})
        last = sum(1 for _, b in phrases if b < fall) - 1                   # any recovery before it, with a phrase to spare
    room = np.arange(1, last)
    count = min(len(room), 2 if skill < TWICE_BELOW and len(phrases) >= 6 else 1)
    picks = sorted(rng.choice(room, size=count, replace=False)) if count else []
    if count == 2 and picks[1] - picks[0] < 2:
        picks = picks[:1]
    for k in picks:
        a, b = phrases[k]
        out.append({'fall': a + (b - a) * rng.uniform(0.25, 0.55), 'cue': phrases[k + 1][0],
                    'order': [str(p) for p in rng.permutation(parts)]})
    return sorted(out, key=lambda c: c['fall'])


def collapse(segments: list[dict], part: str, falls: list[dict], beat: float, rng, log: list,
             written: list[dict] | None = None) -> list[dict]:
    """One singer through the collapses: giving up after the note they're on
    (some sooner than others), and back in when their part's turn comes: the
    brave part at the cue, each other part a beat or two after the one before.
    After the last one at the very lowest, only a try or two at a later
    entrance, given up (from the phrases as written: whatever else they
    would have done there, they never got to)."""
    written = segments if written is None else written
    for c in falls:
        fall = c['fall'] + rng.uniform(-0.6, 0.4) * beat
        if c.get('final'):
            tries, brave = [], c['order'][0] == part
            chance = 0.75 if brave else 0.3
            for k, cue in enumerate(c['cues']):
                if len(tries) < 2 and rng.random() < chance:
                    at = cue + rng.uniform(0, 0.4) * beat * (not brave or k > 0)
                    tries.append((at, at + rng.uniform(0.6, 2.2)))
                chance *= 0.5
            out = []
            for seg in segments:
                a, b = seg['content'][0] / 1000, seg['content'][1] / 1000
                if b <= fall:
                    out.append(seg)
                elif a < fall:
                    cut = end_at(seg, fall)
                    if cut is not None:
                        out.append(cut)
            for t0, t1 in tries:                                            # a try at an entrance, coming to nothing
                for seg in written:
                    a, b = seg['content'][0] / 1000, seg['content'][1] / 1000
                    if a - CONSONANTS <= t0 < b:
                        bit = start_at(seg, t0)
                        bit = end_at(bit, t1) if bit is not None else None
                        if bit is not None:
                            out.append(bit)
                            log.append(f'tries to come back in at {bit["content"][0] / 1000:.1f}s, gives up')
                        break
            segments = out
            continue
        turn = c['order'].index(part)
        back = c['cue'] + (turn * rng.uniform(1.0, 2.0) * beat + rng.uniform(0, 0.15) * beat if turn else 0.0)
        out = []
        for seg in segments:
            a, b = seg['content'][0] / 1000, seg['content'][1] / 1000
            if b <= fall or a >= back - CONSONANTS:                        # (a phrase's consonants start just before its cue)
                out.append(seg)
                continue
            if a < fall:                                                    # given up partway
                cut = end_at(seg, fall)
                if cut is not None:
                    out.append(cut)
            if b > back:                                                    # back in partway
                rejoin = start_at(seg, back)
                if rejoin is not None:
                    out.append(rejoin)
        segments = out
    return segments


# --- pitch: a singer's own pitch curve, with the faults drawn in, sung again ---

def _glide(n: int, start: float, end: float, secs: float) -> np.ndarray:
    k = min(n, max(1, int(secs / FRAME)))
    out = np.full(n, float(end))
    out[:k] = start + (end - start) * (1 - np.cos(np.linspace(0, np.pi, k))) / 2
    return out


def take_curve(audio: np.ndarray, sr: int, seg: dict) -> np.ndarray:
    """The pitch the singer sang over a phrase (Hz per frame, 0 unvoiced),
    from their first take; a frame far off the note (a tracker's octave
    error, or a slip) is put back on it."""
    import pyworld
    rows = _rows(seg)
    frames = int(round(sum(r['secs'] for r in rows) / FRAME))
    t0 = seg['time'][0] / 1000
    x = audio[int(t0 * sr):int(t0 * sr) + int((frames + 2) * FRAME * sr)].astype(np.float64)
    f0 = np.zeros(frames)
    if len(x) > sr * 0.1:
        got, _ = pyworld.harvest(x, sr, frame_period=FRAME * 1000, f0_floor=60, f0_ceil=1100)
        f0[:min(frames, len(got))] = got[:frames]
    for r in rows:
        a, b = int(round((r['at'] - t0) / FRAME)), int(round((r['at'] + r['secs'] - t0) / FRAME))
        if not r['pitch']:
            f0[a:b] = 0
            continue
        hz = 440 * 2 ** ((r['pitch'] - 69) / 12)
        seg_f0 = f0[a:b]
        off = (seg_f0 > 0) & (np.abs(1200 * np.log2(np.maximum(seg_f0, 1) / hz)) > 700)
        seg_f0[off] = hz
    return f0


def fault_curve(f0: np.ndarray, seg: dict, skill: float, rng, k: int, count: int, log: list) -> np.ndarray:
    """The take's pitch curve with this skill's faults, none faster than a
    singer moves: a slow wander, scoops into notes, vibrato calmed on some
    notes, the phrase sagging flat (more as the piece goes on), and below
    WRONG_BELOW notes hunted for (some never found), missed by a lot, and
    wrong ones heard and slid onto the right note."""
    s = severity(skill, COMPETENT)
    w = severity(skill, WRONG_BELOW)
    voiced = f0 > 0
    cents = np.where(voiced, 1200 * np.log2(np.maximum(f0, 1) / 440), 0.0)
    n = len(f0)
    t = np.arange(n) * FRAME
    steps = rng.normal(0, 1, int(n * FRAME / 0.5) + 3)                      # a new leaning every half second or so
    add = np.interp(t, np.arange(len(steps)) * 0.5, np.convolve(steps, np.ones(3) / 3, mode='same')) * WANDER_CENTS * s
    add += -SAG_CENTS * s * k / max(1, count - 1)
    t0 = seg['time'][0] / 1000
    word = lambda r: f'phrase {_number(seg)} "{r["text"]}"'
    for r in _rows(seg):
        if not r['pitch']:
            continue
        a, b = int(round((r['at'] - t0) / FRAME)), min(n, int(round((r['at'] + r['secs'] - t0) / FRAME)))
        m = b - a
        if m < 3:
            continue
        tt = np.arange(m) * FRAME
        if r['kind'] == 2 and rng.random() < 0.15 + 0.5 * s:                  # scooped into from below
            add[a:b] -= SCOOP_CENTS * s * rng.uniform(0.5, 1.0) * np.clip(1 - tt / rng.uniform(0.1, 0.18), 0, 1) ** 2
        edge = 4                                                             # 80 ms: the way in and out of a note left alone
        if m > 3 * edge and rng.random() < 0.1 + 0.5 * s:                    # vibrato calmed: the middle of the note held steadier
            piece = cents[a + edge:b - edge].copy()
            v = piece != 0
            if v.sum() > 8:
                smooth = np.convolve(np.pad(piece, (4, 3), mode='edge'), np.ones(8) / 8, mode='valid')
                hold = rng.uniform(0.5, 0.95) * np.clip(np.minimum(np.arange(len(piece)), np.arange(len(piece))[::-1]) / 4, 0, 1)
                cents[a + edge:b - edge] = np.where(v, piece + (smooth - piece) * hold, 0)
        if w <= 0:
            continue
        if r['pitch'] != r['written']:
            if m * FRAME > 0.35 and rng.random() < 0.3 + 0.5 * w:              # heard it was wrong, and slid onto the right note
                at = int(m * rng.uniform(0.3, 0.6))
                add[a + at:b] += _glide(m - at, 0, 100 * (r['written'] - r['pitch']), rng.uniform(0.12, 0.2))
                log.append(f'{word(r)}: wrong note, slid onto the right one')
            continue
        if m * FRAME < 0.25:
            continue
        roll = rng.random()
        if roll < 0.08 * w:                                                  # missed by a lot, glided there and away
            off = float(rng.uniform(*MISS_SEMITONES)) * (1 if rng.random() < 0.4 else -1)
            edge = rng.uniform(0.08, 0.14)
            add[a:b] += 100 * off * np.minimum(_glide(m, 0, 1, edge), _glide(m, 0, 1, edge)[::-1])
            log.append(f'{word(r)}: missed by {off:+.1f} semitones')
        elif roll < 0.28 * w:                                                # hunted for, from above or below
            found = rng.random() >= 0.3
            tau = rng.uniform(0.25, 0.4) if found else rng.uniform(1.2, 2.0)
            start = rng.uniform(*FALTER_CENTS) * (1 if rng.random() < 0.4 else -1)
            add[a:b] += start * np.exp(-tt / tau) * np.cos(2 * np.pi * rng.uniform(1.0, 1.5) * tt)
            log.append(f'{word(r)}: ' + ('hunted for the note' if found else 'hunted for the note, never found it'))
    return np.where(voiced, 440 * 2 ** ((cents + _slewed(add)) / 1200), 0.0)


def _slewed(x: np.ndarray) -> np.ndarray:
    """x moving no faster than GLIDE allows, from both ends (so nothing lags)."""
    step = GLIDE * FRAME
    fwd = x.copy()
    for i in range(1, len(fwd)):
        fwd[i] = np.clip(fwd[i], fwd[i - 1] - step, fwd[i - 1] + step)
    back = x.copy()
    for i in range(len(back) - 2, -1, -1):
        back[i] = np.clip(back[i], back[i + 1] - step, back[i + 1] + step)
    out = (fwd + back) / 2
    for i in range(1, len(out)):                                              # the average of two can still step too far: once more
        out[i] = np.clip(out[i], out[i - 1] - step, out[i - 1] + step)
    return out


def with_faults(segments: list[dict], audio: np.ndarray, sr: int, skill: float, seed: int, log: list) -> list[dict]:
    """A singer's phrases for the second pass: each carrying the pitch curve to
    sing (their first take's, with this skill's faults), so SoulX sings the
    faults itself."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6007]))
    out = []
    for k, seg in enumerate(segments):
        curve = take_curve(audio, sr, seg)
        notes = np.zeros(len(curve), bool)
        t0 = seg['time'][0] / 1000
        for r in _rows(seg):
            if r['pitch']:
                notes[int(round((r['at'] - t0) / FRAME)):int(round((r['at'] + r['secs'] - t0) / FRAME))] = True
        if (curve[notes] > 0).mean() < 0.3:                                  # left out of the take (the section carried it): out of this one too
            continue
        f0 = fault_curve(curve, seg, skill, rng, k, len(segments), log)
        out.append({**seg, 'f0': ' '.join(f'{v:.1f}' for v in f0)})
    return out


def timing(segments: list[dict], skill: float, seed: int, part: str, falls: list[dict], beat: float, log: list) -> list[dict]:
    """A singer's phrases with this skill's entries, lost places and collapses."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 5521]))
    said = []
    written = segments
    segments = entries(segments, skill, rng, beat, said)
    segments = collapse(segments, part, falls, beat, rng, log, written)
    kept = {f'phrase {_number(seg)}' for seg in segments}
    log[:0] = [line for line in said if line.split(':')[0] in kept]          # nothing about phrases it never got to
    return segments


def describe(falls: list[dict]) -> list[str]:
    out = []
    for c in falls:
        if c.get('final'):
            out.append(f'falls apart for good at {c["fall"]:.1f}s')
        elif len(c['order']) > 1:
            out.append(f'collapse at {c["fall"]:.1f}s; {c["order"][0]} finds the entrance at {c["cue"]:.1f}s, then '
                       + ', '.join(c['order'][1:]))
        else:
            out.append(f'collapse at {c["fall"]:.1f}s; back in at {c["cue"]:.1f}s')
    return out
