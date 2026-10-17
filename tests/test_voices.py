import pytest

from chorale import voices


def bass(): return voices.Voice('b', 'en', low=40, high=60, median=50, source='', dir='')
def tenor(): return voices.Voice('t', 'en', low=48, high=67, median=57, source='', dir='')


def test_in_range_needs_no_shift():
    assert voices.check_range(bass(), [40, 50, 62]) == 0


def test_octave_shift_when_it_fits():
    assert voices.check_range(tenor(), [36, 40, 45]) == 12


def test_out_of_range_names_the_notes():
    with pytest.raises(voices.RangeError, match='D2'):
        voices.check_range(voices.Voice('s', 'en', 60, 72, 66, '', ''), [38, 74, 86])


def test_nobody_is_cast_above_the_ceiling():
    soprano = voices.Voice('s', 'it', 60, 81, 70, '', '', reach=2)
    assert voices.check_range(soprano, [65, 77]) == 0
    with pytest.raises(voices.RangeError):
        voices.check_range(soprano, [62, 79])        # up to G5: out of reach, though the type's range says otherwise
