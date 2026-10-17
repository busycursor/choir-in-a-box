import itertools

import numpy as np
import pytest

from chorale import accompany, pipeline, realize
from chorale.sing_parts import LEAD_IN


@pytest.fixture(scope='module')
def parts(tmp_path_factory):
    from music21 import corpus
    path = tmp_path_factory.mktemp('score') / 'bwv14.5.musicxml'
    corpus.parse('bach/bwv14.5').write('musicxml', fp=str(path))
    return pipeline.build_parts(path, tmp_path_factory.mktemp('parts') / 'parts.json', bpm=72)


def onsets_as_sung(parts, part):
    t, out = LEAD_IN, []
    for midi, secs, *_ in parts['parts'][part]:
        if midi is not None:
            out.append(t)
        t += secs
    return np.array(sorted(set(round(x, 4) for x in out)))


def test_the_accompaniment_is_on_the_choirs_timeline(parts):
    sung = onsets_as_sung(parts, 'Bass')
    for n in accompany.score_notes(parts, 'Bass'):
        assert np.abs(sung - n.start).min() < 0.001    # every bass note where the bass sang it, fermatas and all


def test_the_realization_has_no_parallels_and_stays_under_the_tune(parts):
    chords = realize.chords_from_voices(parts)
    scale, lead = realize.key_info(parts, 'g minor')
    path = realize.realize(chords, lead, seed=0)
    for i in range(1, len(path)):
        a, b = sorted(path[i - 1]), sorted(path[i])
        assert not any(realize._parallel(x1, x2, chords[i - 1].bass, chords[i].bass) for x1, x2 in zip(a, b))
        assert not any(realize._parallel(x1, x2, y1, y2) for (x1, x2), (y1, y2) in itertools.combinations(list(zip(a, b)), 2))
    under = sum(1 for ch, v in zip(chords, path) if ch.melody is None or max(v) <= ch.melody)
    assert under >= 0.95 * len(chords)


def test_a_realization_is_reproducible(parts):
    chords = realize.chords_from_voices(parts)
    assert realize.realize(chords, 1, seed=4) == realize.realize(chords, 1, seed=4)


def test_figures_spell_their_chords():
    c_major = [0, 2, 4, 5, 7, 9, 11]
    spell = lambda bass, fig: realize.chords_from_figures([[0.0, 1.0, bass]], [[0.0, fig]], c_major)[0].pcs
    assert spell(52, '6') == {4, 7, 0}          # E with a 6: E G C
    assert spell(55, '7') == {7, 11, 2, 5}      # G with a 7: G B D F
    assert spell(53, '42') == {5, 7, 11, 2}     # F with 4-2: F G B D
    assert spell(48, '') == {0, 4, 7}           # a bare bass note: its 5/3
    assert spell(57, '#') == {9, 1, 4}          # A with a sharp: the third raised, A C-sharp E


def test_the_form_is_heard_and_the_organ_registers_by_section(parts):
    secs = accompany.sections(parts)
    assert secs[0] == 0 and max(secs) >= 1
    regs, voices = accompany.organ_plan(parts, seed=0)
    assert len(set(regs)) >= 2                       # it changes registration somewhere
    assert regs == accompany.organ_plan(parts, seed=0)[0]


def test_the_organist_is_human_but_reproducible(parts):
    a = accompany.notes_for(parts, 'organ', seed=1, score_key='g minor')
    b = accompany.notes_for(parts, 'organ', seed=1, score_key='g minor')
    assert a == b
    exact = {round(n.start, 4) for n in accompany.score_notes(parts, 'Bass')}
    assert sum(1 for n in a if round(n.start, 4) in exact) < len(a) / 2   # most notes not dead on the grid


def test_harpsichord_chords_are_rolled(parts):
    notes = [n for n in accompany.notes_for(parts, 'harpsichord', seed=0, score_key='g minor') if n.voice == 'rh']
    starts = sorted({round(n.start, 3) for n in notes})
    assert len(starts) > len(notes) * 0.6            # a chord's notes start one after another, not together
