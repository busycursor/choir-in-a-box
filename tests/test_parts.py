import pytest

from chorale import pipeline


@pytest.fixture(scope='module')
def score(tmp_path_factory):
    """Bach's BWV 14.5 from music21's own collection, as a MusicXML file."""
    from music21 import corpus
    path = tmp_path_factory.mktemp('score') / 'bwv14.5.musicxml'
    corpus.parse('bach/bwv14.5').write('musicxml', fp=str(path))
    return path


@pytest.fixture(scope='module')
def parts(score, tmp_path_factory):
    return pipeline.build_parts(score, tmp_path_factory.mktemp('parts') / 'parts.json', bpm=72)


def test_four_german_parts(parts):
    assert parts['lang'] == 'de'                       # told by its lyrics
    assert list(parts['parts']) == ['Soprano', 'Alto', 'Tenor', 'Bass']


def test_every_part_opens_on_the_first_word(parts):
    for notes in parts['parts'].values():
        first = next(n for n in notes if n[2] and n[2] != '<breath>')
        assert first[2].startswith('Wär')


def test_chorale_reading_holds_the_last_note_longest(parts):
    sung = [n for n in parts['parts']['Soprano'] if n[0] is not None]
    beat = 60 / parts['bpm']
    assert sung[-1][1] == pytest.approx(3 * beat, rel=0.02)          # its fermata, whole: no breath taken from it
    assert sung[-1][1] > max(n[1] for n in sung[:-1])


def test_phrases_end_on_the_fermatas(parts):
    assert len(parts['phrases']) == len(parts['timing']['fermatas']) > 1
    for (a, b), (c, _) in zip(parts['phrases'], parts['phrases'][1:]):
        assert a < b < c


def test_literal_sings_it_as_written(score, tmp_path):
    lit = pipeline.build_parts(score, tmp_path / 'lit.json', literal=True)
    assert lit['timing']['fermatas'] == []


def test_stop_ends_everyone_together_on_a_held_chord(score, tmp_path):
    cut = pipeline.build_parts(score, tmp_path / 'cut.json', bpm=72, stop='4.1', literal=True)
    ends = {round(sum(n[1] for n in notes), 3) for notes in cut['parts'].values()}
    assert len(ends) == 1                              # all four parts end at the same moment


def test_transpose_moves_every_part(score, tmp_path):
    plain = pipeline.build_parts(score, tmp_path / 'a.json', bpm=72, literal=True)
    lower = pipeline.build_parts(score, tmp_path / 'b.json', bpm=72, literal=True, transpose=-2)
    first = lambda p, part: next(n[0] for n in p['parts'][part] if n[0] is not None)
    assert all(first(lower, part) == first(plain, part) - 2 for part in plain['parts'])
