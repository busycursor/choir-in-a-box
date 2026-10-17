"""Scores from anywhere: a MusicXML file (.musicxml, .xml, compressed .mxl),
a link to one, or any web page with MusicXML on it.

A page is searched for scores: every link and quoted path in it, and in its
own scripts, that ends in a score's extension (or a .json, which some pages
use to carry MusicXML with other data), including a script's template path
(`data/${id}.json`) filled in from the link's #fragment. Each candidate is
fetched and kept only if it really is a score. A #fragment then picks the
score whose name matches it; a page with one score uses that; otherwise the
choices are listed. Downloads are cached in engine/scores/; a score already
there can be named by its file name, or the end of it ("227.7" for
bwv227.7.json).

Usage: python -m chorale.scores <page|link|file>   (lists the scores found)
"""
import io, json, re, sys, urllib.parse, urllib.request, zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'engine' / 'scores' / 'web'
EXT = ('.musicxml', '.xml', '.mxl', '.json')
MAX_CANDIDATES = 120
MAX_SCRIPTS = 12


@dataclass(frozen=True)
class Score:
    id: str      # its name: the file's stem
    path: Path   # the local copy


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def is_score(data: bytes) -> bool:
    """MusicXML (plain or compressed), or JSON carrying it."""
    if data[:2] == b'PK':
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return False
        return 'META-INF/container.xml' in names or any(n.endswith(('.musicxml', '.xml')) for n in names)
    head = data[:4000].decode('utf-8', errors='replace')
    if '<score-partwise' in head or '<score-timewise' in head or '<!DOCTYPE score-' in head:
        return True
    if head.lstrip().startswith('{'):
        try:
            return 'musicxml' in json.loads(data)
        except ValueError:
            return False
    return False


def _cached(url: str) -> tuple[Path, bytes]:
    u = urllib.parse.urlparse(url)
    rel = u.path.lstrip('/')
    if not rel or rel.endswith('/'):
        rel += 'index.html'   # a folder's page, not a file named like the folder (which would block everything under it)
    path = CACHE / u.netloc / rel
    if path.is_file():
        return path, path.read_bytes()
    data = _get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, data


def candidates(page: str, base: str, fragment: str, scripts: list[str] = ()) -> list[str]:
    """Absolute links to what might be scores, from a page's text and its scripts'."""
    found = []
    for text in [page, *scripts]:
        for m in re.finditer(r'''["'`(=\s]([^"'`()\s<>]+?(?:\.musicxml|\.mxl|\.xml|\.json))["'`)\s]''', text):
            found.append(m.group(1))
        if fragment:  # a script that builds the path from the page's #fragment
            for m in re.finditer(r'[`]([^`]*?)\$\{[^}]+\}([^`]*?(?:\.musicxml|\.mxl|\.xml|\.json))`', text):
                found.append(f'{m.group(1)}{fragment}{m.group(2)}')
    out = []
    for f in found:
        if '${' in f:
            continue
        url = urllib.parse.urljoin(base, f)
        if url not in out:
            out.append(url)
    return out


def cached(name: str) -> list[Score]:
    """Scores already downloaded whose file name is, or ends with, name."""
    found = []
    for f in sorted((ROOT / 'engine' / 'scores').rglob('*')):
        if f.is_file() and f.suffix in EXT and (f.stem == name or f.stem.endswith(name)) and is_score(f.read_bytes()):
            found.append(Score(f.stem, f))
    exact = [s for s in found if s.id == name]
    found = exact or found
    return list({s.id: s for s in found}.values())   # the same name downloaded twice is the same score


def find(ref: str) -> list[Score]:
    """Every score a file, a link, a page, or the name of one already downloaded leads to."""
    p = Path(ref)
    if p.exists():
        return [Score(p.stem, p)]
    if '://' not in ref:
        return cached(ref)
    url, _, fragment = ref.partition('#')
    path, data = _cached(url)
    if is_score(data):
        return [Score(path.stem, path)]
    page = data.decode('utf-8', errors='replace')
    scripts = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page)[:MAX_SCRIPTS]:
        s = urllib.parse.urljoin(url, src)
        if urllib.parse.urlparse(s).netloc == urllib.parse.urlparse(url).netloc:  # the page's own, not libraries
            try:
                scripts.append(_cached(s)[1].decode('utf-8', errors='replace'))
            except OSError:
                pass
    links = candidates(page, url, fragment, scripts)
    if fragment:  # try the ones named for it first, and only those if there are any
        named = [c for c in links if Path(urllib.parse.urlparse(c).path).stem.lower() == fragment.lower()]
        links = named or links
    found = []
    for c in links[:MAX_CANDIDATES]:
        try:
            cpath, cdata = _cached(c)
        except OSError:
            continue
        if is_score(cdata):
            found.append(Score(cpath.stem, cpath))
    return found


def resolve(ref: str) -> Score:
    """The one score a reference means; ValueError listing the choices if it's ambiguous."""
    found = find(ref)
    if not found:
        raise ValueError(f'no MusicXML found at {ref}')
    fragment = ref.partition('#')[2].lower()
    if fragment:
        named = [s for s in found if s.id.lower() == fragment]
        if named:
            return named[0]
    if len(found) == 1:
        return found[0]
    raise ValueError(f'{len(found)} scores at {ref}; add #<name> for one, or --all: ' + ', '.join(s.id for s in found))


if __name__ == '__main__':
    for s in find(sys.argv[1]):
        print(f'{s.id:24} {s.path}')
