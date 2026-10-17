import json

import numpy as np
import pytest

from chorale import choir_skill, pipeline
from chorale.sing_parts import target


@pytest.fixture(scope='module')
def parts(tmp_path_factory):
    from music21 import corpus
    path = tmp_path_factory.mktemp('score') / 'bwv14.5.musicxml'
    corpus.parse('bach/bwv14.5').write('musicxml', fp=str(path))
    return pipeline.build_parts(path, tmp_path_factory.mktemp('parts') / 'parts.json', bpm=72)


def sung(parts, part='Soprano'):
    return target(parts['parts'][part], 0)


def test_a_fine_choir_sings_what_is_written(parts):
    segs = sung(parts)
    scale = choir_skill.scale_of(parts['parts'])
    assert choir_skill.mangle(segs, 1.0, 0, scale) == segs
    assert choir_skill.mangle(segs, 0.6, 0, scale) == segs


def test_the_scale_of_a_g_minor_chorale(parts):
    assert set(choir_skill.scale_of(parts['parts'])) >= {7, 10, 2, 0}   # G, B flat, D, C


def test_a_weak_choir_sings_wrong_notes_and_slips_its_words(parts):
    segs = sung(parts)
    scale = choir_skill.scale_of(parts['parts'])
    changed = lambda level, key: sum(a[key] != b[key] for a, b in zip(segs, choir_skill.mangle(segs, level, 0, scale)))
    assert changed(0.1, 'note_pitch') > 0 and changed(0.1, 'phoneme') > 0
    wrong = lambda level: sum(x != y for a, b in zip(segs, choir_skill.mangle(segs, level, 3, scale))
                              for x, y in zip(a['note_pitch'].split(), b['note_pitch'].split()))
    assert wrong(0.05) > wrong(0.4)


def test_wrong_notes_are_near_misses_and_rests_stay_rests(parts):
    segs = sung(parts)
    for a, b in zip(segs, choir_skill.mangle(segs, 0.0, 1, choir_skill.scale_of(parts['parts']))):
        for x, y in zip(map(int, a['note_pitch'].split()), map(int, b['note_pitch'].split())):
            assert (x == 0) == (y == 0) and abs(x - y) <= 2


def test_every_singer_errs_their_own_way(parts):
    segs = sung(parts)
    scale = choir_skill.scale_of(parts['parts'])
    one = choir_skill.mangle(segs, 0.2, choir_skill.singer_seed(0, 'soprano-1'), scale)
    two = choir_skill.mangle(segs, 0.2, choir_skill.singer_seed(0, 'soprano-2'), scale)
    assert one != two
    assert one == choir_skill.mangle(segs, 0.2, choir_skill.singer_seed(0, 'soprano-1'), scale)   # and reproducibly


def test_wrong_notes_remember_what_was_written(parts):
    segs = sung(parts)
    for a, b in zip(segs, choir_skill.mangle(segs, 0.1, 0, choir_skill.scale_of(parts['parts']))):
        assert b['written'] == a['note_pitch']


def notes_of(seg):
    return [r for r in choir_skill._sung(seg) if r['pitch']]


def test_a_late_entry_takes_the_phrase_up_on_a_later_note(parts):
    seg = sung(parts)[1]
    first = notes_of(seg)
    late = choir_skill.start_at(seg, first[2]['at'])
    got = notes_of(late)
    assert got[0]['at'] == pytest.approx(first[2]['at'], abs=0.002) and len(got) == len(first) - 2
    assert late['note_type'].split()[1] == '2'                               # opening on a sung syllable
    assert late['time'][0] / 1000 == pytest.approx(first[2]['at'] - choir_skill.RUN_UP, abs=0.002)
    assert len(late['duration'].split()) == len(late['note_pitch'].split()) == len(late['phoneme'].split())


def test_giving_up_finishes_the_note_or_trims_it(parts):
    seg = sung(parts)[1]
    first = notes_of(seg)
    mid = first[3]['at'] + 0.05
    whole = choir_skill.end_at(seg, mid)
    assert len(notes_of(whole)) == 4 and whole['content'][1] / 1000 == pytest.approx(first[3]['at'] + first[3]['secs'], abs=0.002)
    trimmed = choir_skill.end_at(seg, first[3]['at'] + first[3]['secs'] * 0.5 + 0.1, trim=True)
    assert trimmed['content'][1] / 1000 <= first[3]['at'] + first[3]['secs'] * 0.5 + 0.1 + 0.002


def test_nothing_moves_in_time_for_a_fair_choir(parts):
    segs = sung(parts)
    assert choir_skill.timing(segs, 0.5, 0, 'Soprano', [], 60 / 72, []) == segs


def test_a_weak_choir_enters_late_early_or_not_at_all(parts):
    segs = sung(parts)
    said = []
    for seed in range(6):
        choir_skill.timing(segs, 0.1, seed, 'Soprano', [], 60 / 72, said)
    assert any('late' in l for l in said) and any('early' in l or 'sat it out' in l or 'behind' in l for l in said)


def test_the_choir_collapses_only_at_the_very_lowest(parts):
    phrases = [tuple(p) for p in parts['phrases']]
    assert choir_skill.collapses(phrases, 0.2, 0, ['Soprano', 'Alto']) == []
    falls = choir_skill.collapses(phrases, 0.1, 0, ['Soprano', 'Alto'])
    assert len(falls) == 1
    c = falls[0]
    assert c['fall'] < c['cue'] and c['cue'] in [a for a, _ in phrases] and sorted(c['order']) == ['Alto', 'Soprano']


def sounding(segs, t):
    return any(n['at'] <= t < n['at'] + n['secs'] for s in segs for n in notes_of(s))


def test_after_a_collapse_one_part_finds_the_entrance_first(parts):
    offset = 0.5
    phrases = [(a + offset, b + offset) for a, b in parts['phrases']]
    c = choir_skill.collapses(phrases, 0.1, 0, ['Soprano', 'Alto'])[0]
    sang = {p: choir_skill.collapse(sung(parts, p), p, [c], 60 / 72, np.random.default_rng(1), []) for p in ('Soprano', 'Alto')}
    mid = (c['fall'] + c['cue']) / 2
    assert not any(sounding(s, mid) for s in sang.values())                  # everyone stopped
    brave, other = c['order']
    entrance = min(n['at'] for s in sung(parts, brave) for n in notes_of(s) if n['at'] >= c['cue'] - 0.05)
    assert any(abs(n['at'] - entrance) < 0.05 for s in sang[brave] for n in notes_of(s))   # the brave part in at its entrance
    assert not sounding(sang[other], entrance + 0.2)                         # the rest not yet


def test_at_skill_zero_it_falls_apart_for_good(parts):
    phrases = [tuple(p) for p in parts['phrases']]
    begin, end = phrases[0][0], phrases[-1][1]
    for seed in range(8):
        falls = choir_skill.collapses(phrases, 0.0, seed, ['Soprano', 'Alto', 'Tenor', 'Bass'])
        final = [c for c in falls if c.get('final')]
        assert len(final) == 1
        f = final[0]['fall']
        lo, hi = choir_skill.FALLS_APART
        assert begin + lo * (end - begin) <= f <= begin + hi * (end - begin)
        assert all(c['cue'] < f for c in falls if not c.get('final'))     # any recovery comes before it
    assert not any(c.get('final') for c in choir_skill.collapses(phrases, 0.1, 0, ['Soprano', 'Alto']))


def test_after_falling_apart_only_brief_tries(parts):
    offset = 0.5
    phrases = [(a + offset, b + offset) for a, b in parts['phrases']]
    final = next(c for c in choir_skill.collapses(phrases, 0.0, 0, ['Soprano']) if c.get('final'))
    segs = choir_skill.collapse(sung(parts), 'Soprano', [final], 60 / 72, np.random.default_rng(0), [])
    after = [n for s in segs for n in notes_of(s) if n['at'] > final['fall'] + 1.0]
    assert sum(n['secs'] for n in after) < 2 * 2.2 + 2                         # a try or two, no more


def take_of(seg, sr=24000):
    """A stand-in take: a pure tone on each written note, silent between."""
    out = np.zeros(int((seg['time'][1] / 1000 + 1) * sr))
    for n in notes_of(seg):
        a, b = int(n['at'] * sr), int((n['at'] + n['secs']) * sr)
        phase = 2 * np.pi * 440 * 2 ** ((n['pitch'] - 69) / 12) * np.arange(b - a) / sr
        out[a:b] = sum(0.3 / h * np.sin(h * phase) for h in range(1, 6))       # a few harmonics, like a voice
    return out


def test_the_take_curve_follows_the_notes(parts):
    seg = sung(parts)[1]
    f0 = choir_skill.take_curve(take_of(seg), 24000, seg)
    assert len(f0) == round(sum(map(float, seg['duration'].split())) / choir_skill.FRAME)
    n = notes_of(seg)[2]
    a = int(round((n['at'] - seg['time'][0] / 1000) / choir_skill.FRAME))
    hz = 440 * 2 ** ((n['pitch'] - 69) / 12)
    assert abs(1200 * np.log2(np.median(f0[a + 3:a + 8]) / hz)) < 30


def test_faults_are_drawn_no_faster_than_a_singer_moves(parts):
    seg = sung(parts)[1]
    f0 = choir_skill.take_curve(take_of(seg), 24000, seg)
    for seed in range(5):
        out = choir_skill.fault_curve(f0, seg, 0.0, np.random.default_rng(seed), 1, 6, [])
        assert ((out > 0) == (f0 > 0)).all()                                 # voiced where the take was, and only there
        c = np.where(out > 0, 1200 * np.log2(np.maximum(out, 1) / np.maximum(f0, 1)), 0)
        both = (out[1:] > 0) & (out[:-1] > 0)
        assert np.abs(np.diff(c))[both].max() <= choir_skill.GLIDE * choir_skill.FRAME + 1   # never faster than a singer glides, beyond the take's own moves


def test_a_fair_choir_is_only_a_little_pitchy(parts):
    seg = sung(parts)[1]
    f0 = choir_skill.take_curve(take_of(seg), 24000, seg)
    log = []
    out = choir_skill.fault_curve(f0, seg, 0.5, np.random.default_rng(0), 1, 6, log)
    c = np.where(f0 > 0, 1200 * np.log2(np.maximum(out, 1) / np.maximum(f0, 1)), 0)
    assert np.abs(c).max() < 60 and not log                                  # no hunting, no misses at 0.5


def test_a_phrase_left_out_of_the_take_is_left_out_again(parts):
    segs = sung(parts)[:3]
    take = take_of(segs[0])
    full = np.zeros(int((segs[-1]['time'][1] / 1000 + 1) * 24000))
    full[:len(take)] = take[:len(full)]
    for s in segs[2:]:
        t = take_of(s)
        a = int(s['time'][0] / 1000 * 24000)
        full[a:len(t)] += t[a:len(full)]
    out = choir_skill.with_faults(segs, full, 24000, 0.3, 0, [])
    assert [s['index'] for s in out] == [segs[0]['index'], segs[2]['index']] and all('f0' in s for s in out)


def test_a_try_at_an_entrance_keeps_the_entrance_note(parts):
    seg = sung(parts)[1]
    first = notes_of(seg)[0]
    cue = first['at'] + 0.1                                                  # the note starts early for its consonants
    bit = choir_skill.end_at(choir_skill.start_at(seg, cue), cue + 0.6)
    assert bit is not None and notes_of(bit)[0]['at'] == pytest.approx(first['at'], abs=0.002)


def test_a_try_comes_from_the_phrase_as_written(parts):
    offset = 0.5
    phrases = [(a + offset, b + offset) for a, b in parts['phrases']]
    segs = sung(parts)
    final = {'fall': phrases[2][0] + 1.0, 'final': True, 'cues': [phrases[3][0]], 'order': ['Soprano']}
    for seed in range(20):                                                   # the brave part tries, though it had dropped that phrase
        log = []
        out = choir_skill.collapse(segs[:3], 'Soprano', [final], 60 / 72, np.random.default_rng(seed), log, segs)
        if log:
            assert any(s['index'] == segs[3]['index'] for s in out)
            return
    assert False, 'never tried'
