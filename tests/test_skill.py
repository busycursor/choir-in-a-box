import numpy as np
import pytest

from chorale import accompany, pipeline, skill
from chorale.sing_parts import LEAD_IN


@pytest.fixture(scope='module')
def parts(tmp_path_factory):
    from music21 import corpus
    path = tmp_path_factory.mktemp('score') / 'bwv14.5.musicxml'
    corpus.parse('bach/bwv14.5').write('musicxml', fp=str(path))
    return pipeline.build_parts(path, tmp_path_factory.mktemp('parts') / 'parts.json', bpm=72)


def performed(parts, instrument, level, seed=0):
    notes = accompany.notes_for(parts, instrument, seed=seed, score_key='g minor', skill=level)
    phrases = [(LEAD_IN + a, LEAD_IN + b) for a, b in parts['phrases']]
    return skill.perform(notes, level, seed, accompany.realize_scale(parts, 'g minor'), phrases)


def test_never_tighter_than_a_competent_player():
    assert skill.looseness(1.0) == skill.looseness(0.6) == 1.0
    assert skill.looseness(0.3) > 1.0 and skill.looseness(0.0) > skill.looseness(0.3)


def test_a_skilled_harpsichordist_ornaments_more(parts):
    # counted before any mistakes (a weak player's corrected wrong notes add notes too)
    played = lambda level: len(accompany.notes_for(parts, 'harpsichord', seed=0, score_key='g minor', skill=level))
    assert played(0.95) > played(0.8) > played(0.6) > played(0.35)


def test_a_weak_player_plays_notes_that_arent_there(parts):
    written = {n.midi for n in performed(parts, 'piano', 0.6)}
    weak = performed(parts, 'piano', 0.2)
    assert sum(1 for n in weak if n.midi not in written) >= 5


def test_a_very_weak_player_stops_and_searches(parts):
    notes = performed(parts, 'harpsichord', 0.05, seed=2)
    starts = sorted(n.start for n in notes if n.velocity > 0.4)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert max(gaps) > 0.8                                    # it stops
    assert any(abs(n.velocity - 0.35) < 1e-6 for n in notes)  # and looks for its place with quiet notes


def test_any_performance_is_reproducible(parts):
    for level in (0.05, 0.3, 0.6, 0.95):
        assert performed(parts, 'harpsichord', level, seed=4) == performed(parts, 'harpsichord', level, seed=4)


def test_a_player_who_cant_manage_it_fumbles_throughout(parts):
    weak = performed(parts, 'harpsichord', 0.05, seed=3)
    shaky = performed(parts, 'harpsichord', 0.3, seed=3)
    written = sorted(n.start for n in performed(parts, 'harpsichord', 0.6, seed=3))
    late = lambda notes: np.mean([min(abs(np.array(written) - n.start)) > 0.15 for n in notes])
    assert late(weak) > 2 * late(shaky)                     # off the beat everywhere, not in one place
    assert len(weak) < 0.8 * len(performed(parts, 'harpsichord', 0.6, seed=3))   # notes and chords dropped
    assert np.mean([n.velocity for n in weak]) < np.mean([n.velocity for n in shaky])   # timid
