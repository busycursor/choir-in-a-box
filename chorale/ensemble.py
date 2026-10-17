"""The choir and the accompanist falling apart together, or not: one plan, so
each reacts to the other (choir_skill.py and skill.py carry it out). Every
time in it is a place in the score as the tempo map has it, so whoever is
playing or singing is always where the piece is meant to be: an accompanist
rallying on alone, or coming in early to lead the choir back, plays the bars
that belong there.

- The choir collapses (choir skill below choir_skill.COLLAPSE_BELOW): a good
  accompanist (CARRIES_ON and up) plays straight on, and the choir finds it
  at the next entrance. A weaker one plays on harder for a while to rally
  them (a few beats), gives up, and comes back in at the entrance, or a bar or so before it
  to get the choir going.
- The choir falls apart for good (choir skill 0): once everyone stops singing
  the accompanist stops too, after a beat or two of rallying them (five or
  six at best); a poor one may lose its place first and take them down with
  it. A good one may try once more, leading in to a later entrance, which the
  choir's last tries answer; nobody follows, and that's the end.
- Both lost (each below LOST_TOGETHER): nobody can find the first entrance
  after a collapse, so the choir only comes back at the one after.
- The accompanist breaks down (skill.BREAKDOWN_BELOW): a weak choir falls
  with it (the weaker, the likelier), coming back when it does; a good choir
  sings on.
"""
import copy

import numpy as np

from chorale import choir_skill, skill

CARRIES_ON = 0.45      # an accompanist this good plays straight through a choir's collapse
LOST_TOGETHER = 0.07   # both below this: the first entrance after a collapse goes by


def _cue_after(phrases: list[tuple[float, float]], t: float) -> float | None:
    return next((a for a, _ in phrases if a > t), None)


def plan(choir: float, accompanist: float | None, phrases: list[tuple[float, float]], parts: list[str], seed: int,
         beat: float, sung: list[dict] | None = None) -> dict:
    """{'choir': its collapses (choir_skill.collapse), 'accompanist': its events
    (skill.perform), 'log': what happens}. phrases in render seconds. Made
    before the singing (the choir sings its part of it); sung, the collapses
    a render already sang, for an accompanist chosen afterwards: it reacts to
    them, and they stay as they are."""
    falls = choir_skill.collapses(phrases, choir, seed, parts) if sung is None else copy.deepcopy(sung)
    if accompanist is None:
        return {'choir': falls, 'accompanist': [], 'log': [], 'accompanist_skill': None}
    rng = np.random.default_rng(np.random.SeedSequence([seed, 4242]))
    events, log = [], []
    end = next((c['fall'] for c in falls if c.get('final')), float('inf'))
    for c in falls:
        if c.get('final'):
            if accompanist < skill.BREAKDOWN_BELOW and rng.random() < 0.5:     # it loses the place first, and takes them down with it
                stop = c['fall'] - rng.uniform(0.3, 1.5) * beat
                events.append({'kind': 'breakdown', 'a': stop - rng.uniform(1, 2) * beat, 'b': stop, 'stop': stop, 'resume': stop,
                               'shift': int(rng.choice([-2, -1, 1, 2, 5]))})
                ev = {'kind': 'give_up', 'fall': c['fall'], 'rally': stop, 'stop': stop, 'tries': []}
                log.append(f'the accompanist loses its place at {stop:.1f}s, and everyone stops with it')
            else:                                                             # it plays on a little to rally them, then stops too
                stop = c['fall'] + (1 + 5 * accompanist) * beat * rng.uniform(0.8, 1.2)
                ev = {'kind': 'give_up', 'fall': c['fall'], 'rally': c['fall'], 'stop': stop, 'tries': []}
                log.append(f'the accompanist plays on to rally them, gives up at {stop:.1f}s')
            cue = _cue_after(phrases, stop + 5 * beat)                         # a pause, then a lead-in of up to 4 beats
            if cue is not None and rng.random() < 0.8 * accompanist:     # one more try, leading in to an entrance
                t0 = cue - rng.uniform(2, 4) * beat
                ev['tries'].append((t0, cue + rng.uniform(1.5, 3.0)))
                c['cues'] = [a for a, _ in phrases if a >= cue]                   # the choir's last tries answer it
                log.append(f'the accompanist tries to lead them back in at {t0:.1f}s, for the entrance at {cue:.1f}s')
            events.append(ev)
            continue
        if choir < LOST_TOGETHER and accompanist < LOST_TOGETHER:              # nobody finds the first entrance
            later = _cue_after(phrases, c['cue'] + 0.1)
            if later is not None and later < end:
                log.append(f'nobody finds the entrance at {c["cue"]:.1f}s')
                c['cue'] = later
        if accompanist >= CARRIES_ON:
            log.append(f'the accompanist plays straight on through the collapse at {c["fall"]:.1f}s')
            continue
        stop = c['fall'] + (1 + 4 * accompanist) * beat * rng.uniform(0.7, 1.3)
        early = rng.random() < 0.3 + accompanist
        back = c['cue'] - rng.uniform(2, 4) * beat if early else c['cue']
        if back - stop < 2 * beat:                                            # no time to give up and come back: plays on
            log.append(f'the accompanist plays on through the collapse at {c["fall"]:.1f}s, just')
            continue
        events.append({'kind': 'give_up', 'fall': c['fall'], 'rally': c['fall'], 'stop': stop, 'back': back})
        log.append(f'the accompanist plays on to rally them, gives up at {stop:.1f}s, back at {back:.1f}s'
                   + (' to get them going' if early else ''))
    for sp in skill.breakdown_spans(accompanist, np.random.default_rng(np.random.SeedSequence([seed, 313])), phrases):
        if sp['a'] >= end or any(e['rally'] <= sp['resume'] and sp['a'] <= e.get('back', end) for e in events if e['kind'] == 'give_up'):
            continue                                                          # it's already given up there
        if sung is not None:                                                 # the choir can't fall with it now
            if not any(c['fall'] <= sp['stop'] <= c.get('cue', end) for c in falls):
                events.append(sp)
                log.append(f'the accompanist breaks down at {sp["stop"]:.1f}s; the choir sings on')
            continue
        events.append(sp)
        if any(c['fall'] <= sp['stop'] <= c.get('cue', end) for c in falls):   # the choir's already down
            log.append(f'the accompanist breaks down too, at {sp["stop"]:.1f}s, back at {sp["resume"]:.1f}s')
            continue
        if rng.random() < choir_skill.severity(choir, choir_skill.WRONG_BELOW):
            fall = sp['stop'] + rng.uniform(0.5, 2.0) * beat
            if fall < sp['resume']:
                falls.append({'fall': fall, 'cue': sp['resume'], 'order': [str(p) for p in rng.permutation(parts)], 'breakdown': sp})
                log.append(f'the accompanist breaks down at {sp["stop"]:.1f}s and the choir falls with it, back at {sp["resume"]:.1f}s')
                continue
        log.append(f'the accompanist breaks down at {sp["stop"]:.1f}s; the choir sings on')
    if sung is not None:                                                     # breakdowns the choir fell with, played as they were
        for c in sung:
            if 'breakdown' in c:
                events.append(c['breakdown'])
                log.append(f'the accompanist breaks down at {c["breakdown"]["stop"]:.1f}s, where the choir fell with it')
        falls = sung
    return {'choir': sorted(falls, key=lambda c: c['fall']), 'accompanist': events, 'log': log, 'accompanist_skill': accompanist}
