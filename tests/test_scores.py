from pathlib import Path

import pytest

from chorale import scores

WEB = Path(__file__).parent / 'fixtures' / 'web'
SITE = 'https://scores.example.org/'
FILES = {SITE: 'page.html', SITE + 'page.html': 'page.html', SITE + 'app.js': 'app.js', SITE + 'scores/song.musicxml': 'score.musicxml',
         SITE + 'notes.json': 'notes.json', SITE + 'data/hymn.json': 'data.json'}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def get(url):
        if url not in FILES:
            raise OSError(f'not found: {url}')
        return (WEB / FILES[url]).read_bytes()
    monkeypatch.setattr(scores, '_get', get)
    monkeypatch.setattr(scores, 'CACHE', tmp_path)


def test_a_file_is_its_own_score():
    s = scores.resolve(str(WEB / 'score.musicxml'))
    assert s.id == 'score'


def test_a_direct_link_is_a_score():
    assert scores.resolve(SITE + 'scores/song.musicxml').id == 'song'


def test_a_page_finds_its_scores_and_skips_what_isnt_one():
    found = {s.id for s in scores.find(SITE + 'page.html')}
    assert found == {'song'}                      # notes.json is JSON but carries no MusicXML; cover.png isn't looked at


def test_a_fragment_fills_in_a_scripts_template_path():
    assert scores.resolve(SITE + 'page.html#hymn').id == 'hymn'   # data/${id}.json in app.js


def test_compressed_musicxml_counts():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('META-INF/container.xml', '<container/>')
        z.writestr('song.musicxml', (WEB / 'score.musicxml').read_text())
    assert scores.is_score(buf.getvalue())


def test_nothing_found_says_so():
    with pytest.raises(ValueError, match='no MusicXML'):
        scores.resolve(SITE + 'notes.json')


def test_a_page_at_the_sites_root_finds_scores_under_it():
    # the page is the folder itself (it ends in /), and its scores live under that folder
    assert scores.resolve(SITE + '#hymn').id == 'hymn'
    assert {s.id for s in scores.find(SITE)} == {'song'}
