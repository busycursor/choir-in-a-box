import pytest

from chorale.timing import TempoMap

BPM, SEC = 60, 1.0  # a quarter is a second, as written


def chorale():
    # 4/4, two phrases: fermatas on beat 3 of bar 2 (q 6-8) and at the end (q 14-16)
    return TempoMap(BPM, 4.0, 16.0, fermatas=[(6.0, 8.0), (14.0, 16.0)])


def length(tm, a, b):
    return tm.end(b) - tm.start(a)


def test_literal_is_as_written():
    tm = TempoMap(BPM, 4.0, 16.0)
    assert length(tm, 0, 16) == pytest.approx(16.0)


def test_an_inner_fermata_is_held_half_as_long_again():
    assert length(chorale(), 6, 8) == pytest.approx(2.0 * TempoMap.FERMATA, rel=1e-3)


def test_the_last_fermata_is_held_longest():
    assert length(chorale(), 14, 16) == pytest.approx(2.0 * TempoMap.FINAL, rel=1e-3)


def test_slowing_into_a_cadence_and_a_tempo_after():
    tm = chorale()
    assert length(tm, 5, 6) > 1.0 + 0.02      # the beat into the fermata, broadened
    assert length(tm, 4, 5) == pytest.approx(1.0)
    assert length(tm, 8, 9) == pytest.approx(1.0)   # back in tempo


def test_the_last_bar_broadens_more_than_an_inner_cadence():
    tm = chorale()
    assert length(tm, 13, 14) > length(tm, 5, 6)
    assert length(tm, 10, 11) > 1.0   # the slowing reaches back across the last bar


def test_round_trips_through_json():
    tm = chorale()
    again = TempoMap.from_json(tm.to_json())
    assert again.start(15) == pytest.approx(tm.start(15))
