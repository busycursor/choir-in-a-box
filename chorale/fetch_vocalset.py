"""Download just the parts of VocalSet this needs: its sung excerpts, the
singers' readme and the score they sang from (from VocalSet 1.1, a 2 GB
zip), and the note-by-note annotations of those excerpts (from
Annotated-VocalSet, a 400 MB zip). Each zip's directory is read over HTTP
range requests, then only the wanted files are fetched, several at a time,
so about 270 MB comes down instead of 2.4 GB.

  VocalSet: Wilkins, Seetharaman, Wahl & Pardo, ISMIR 2018. CC BY 4.0. zenodo.org/records/1442513
  Annotated-VocalSet: Faghih & Timoney, Applied Sciences 2022. CC BY 4.0. zenodo.org/records/7061507

Usage: python -m chorale.fetch_vocalset   (into engine/datasets/vocalset/; files already there are skipped)
"""
import http.client, io, struct, time, urllib.request, zipfile, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'engine' / 'datasets' / 'vocalset'
VOCALSET = 'https://zenodo.org/api/records/1442513/files/VocalSet11.zip/content'
ANNOTATED = 'https://zenodo.org/api/records/7061507/files/Annotated%20VocalSet.zip/content'
EXCERPTS = ('caro', 'dona', 'row')
WORKERS = 8


def _range(url: str, a: int, b: int) -> bytes:
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={'Range': f'bytes={a}-{b}'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except (OSError, http.client.HTTPException):   # a connection dropped mid-file is the latter
            if attempt == 7:
                raise
            time.sleep(3 * (attempt + 1))


class _Remote(io.RawIOBase):
    """A remote file, read by range, for zipfile to find its directory in."""
    def __init__(self, url):
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60) as r:
            self.url, self.n, self.p = url, int(r.headers['Content-Length']), 0
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.p
    def seek(self, o, w=0):
        self.p = {0: o, 1: self.p + o, 2: self.n + o}[w]; return self.p
    def readinto(self, b):
        k = min(len(b), self.n - self.p)
        if k <= 0: return 0
        d = _range(self.url, self.p, self.p + k - 1); b[:len(d)] = d; self.p += len(d); return len(d)


def fetch(url: str, want) -> int:
    z = zipfile.ZipFile(io.BufferedReader(_Remote(url), buffer_size=1 << 16))
    items = [i for i in z.infolist() if not i.filename.startswith('__MACOSX') and not i.filename.endswith('/') and want(i.filename)]

    def one(i):
        dst = OUT / i.filename
        if dst.exists() and dst.stat().st_size == i.file_size:
            return 0
        raw = _range(url, i.header_offset, i.header_offset + 30 + len(i.filename.encode()) + 1024 + i.compress_size)
        n, e = struct.unpack('<HH', raw[26:30])
        data = raw[30 + n + e:30 + n + e + i.compress_size]
        data = data if i.compress_type == 0 else zlib.decompress(data, -15)
        assert len(data) == i.file_size, i.filename
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return 1

    with ThreadPoolExecutor(WORKERS) as ex:
        return sum(ex.map(one, items))


def main() -> None:
    audio = lambda n: ('/excerpts/' in n and n.endswith('.wav')) or n.endswith(('.txt', '.pdf'))
    notes = lambda n: (n.startswith('Annotated VocalSet/extended 1/with file header/') and n.endswith('.csv')
                       and any(f'_{e}_' in n.lower() for e in EXCERPTS) and 'spoken' not in n)
    print('VocalSet excerpts:', fetch(VOCALSET, audio), 'new', flush=True)
    print('Annotated-VocalSet notes:', fetch(ANNOTATED, notes), 'new', flush=True)


if __name__ == '__main__':
    main()
