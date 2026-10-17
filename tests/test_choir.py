import json

import pytest

from chorale import choir, voices


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, 'INDEX', tmp_path / 'voices')
    monkeypatch.setattr(choir, 'CHOIRS', tmp_path / 'choirs')
    monkeypatch.setattr(choir, 'TEMPOS', tmp_path / 'tempos.json')
    for name, lo, hi in (('s1', 64, 72), ('b1', 40, 58)):
        voices.save(voices.Voice(name, 'en', lo, hi, (lo + hi) // 2, '', f'/v/{name}'))
    (tmp_path / 'choirs').mkdir()
    return tmp_path


def write_choir(lib, cast):
    (lib / 'choirs' / 'test.json').write_text(json.dumps(cast))


def test_tempo_default_is_72(lib):
    assert choir.tempo('bwv14.5', None) == 72


def test_tempo_from_table(lib):
    (lib / 'tempos.json').write_text('{"bwv14.5": 60}')
    assert choir.tempo('bwv14.5', None) == 60


def test_tempo_flag_wins(lib):
    (lib / 'tempos.json').write_text('{"bwv14.5": 60}')
    assert choir.tempo('bwv14.5', 80) == 80


def test_missing_voice_is_named(lib):
    write_choir(lib, {'Soprano': ['nobody']})
    with pytest.raises(KeyError, match='nobody'):
        choir.load_choir('test')


def test_cast_checks_ranges(lib):
    write_choir(lib, {'Soprano': ['s1'], 'Bass': ['s1']})
    parts = {'Soprano': [[67, 1, 'a', '', 2, 0, 1]], 'Bass': [[40, 1, 'a', '', 2, 0, 1]]}
    with pytest.raises(voices.RangeError, match='Bass'):
        choir.cast(choir.load_choir('test'), parts)


def test_cast_gives_prompt_and_shift(lib):
    write_choir(lib, {'Soprano': ['s1'], 'Bass': ['b1']})
    parts = {'Soprano': [[67, 1, 'a', '', 2, 0, 1]], 'Bass': [[45, 1, 'a', '', 2, 0, 1]]}
    assert choir.cast(choir.load_choir('test'), parts) == {'Soprano': [('/v/s1', 0)], 'Bass': [('/v/b1', 0)]}


def test_section_singer_out_of_range_sits_out(lib):
    write_choir(lib, {'Soprano': ['s1'], 'Bass': ['b1', 's1']})
    parts = {'Soprano': [[67, 1, 'a', '', 2, 0, 1]], 'Bass': [[40, 1, 'a', '', 2, 0, 1]]}
    out = []
    assert choir.cast(choir.load_choir('test'), parts, out) == {'Soprano': [('/v/s1', 0)], 'Bass': [('/v/b1', 0)]}
    assert len(out) == 1 and out[0].startswith('Bass: s1')


def test_section_never_sings_an_octave_off(lib):
    voices.save(voices.Voice('t1', 'en', 48, 62, 55, '', '/v/t1'))   # sings the line as written
    voices.save(voices.Voice('s2', 'en', 62, 74, 68, '', '/v/s2'))   # could only sing it an octave up
    write_choir(lib, {'Tenor': ['t1', 's2']})
    parts = {'Tenor': [[52, 1, 'a', '', 2, 0, 1], [57, 1, 'a', '', 2, 0, 1]]}
    out = []
    assert choir.cast(choir.load_choir('test'), parts, out) == {'Tenor': [('/v/t1', 0)]}
    assert 'octave' in out[0]
