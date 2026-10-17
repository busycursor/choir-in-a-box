"""A score's sung parts as syllable-level notes for sing_parts.py.

Takes a MusicXML file (plain or compressed), or a page's data file that
carries MusicXML (JSON with a "musicxml" field, and perhaps a playback
"timeline" of bars). Follows repeats and endings (the timeline if there is one,
else music21's expansion), takes the text part's lyrics line by pass, and
lays them onto every sung part by timing (a cast, several parts with no
--text and no soprano, each sings its own part's words): a held note is re-sung on each new
syllable, notes between syllables carry the syllable on (a melisma), and a
note with no text before it rests. Chord symbols are skipped.

Usage (from the repo root):
  engine/soulx/.venv/bin/python chorale/score_parts.py <score> <parts.json> \\
      [--bpm=72] [--parts=Soprano,Alto,Tenor,Bass] [--text=Soprano] [--lang=de|en] [--intro=2] [--rubato] [--swing] [--literal]
      [--stop=<bar>.<beat>] [--transpose=<semitones>]
Timing (timing.py): --intro=N leaves N bars of silence first, for an accompaniment
(the first full bars; a pickup comes in on the intro's last beats); --swing
swings the eighths;
--rubato leans into phrase ends and broadens the last two bars. A score with
fermatas is read as a chorale is sung instead (timing.py: slowing into each
fermata, held longer, the last one broadest); --literal sings it as written,
and --rubato reads it as a song. The tempo map
goes into the parts file.
Pronunciations: a <score>.say file next to the score, one "word = ARPAbet" per
line (bass = B EY1 S), overrides the dictionary; the exporter lists every
English word it guessed or that has more than one pronunciation, to check.
Defaults: the bpm in the data (else 72); SATB with the soprano's text if
there's a soprano, else every part that has lyrics; German for a chorale
timeline, else English.

Phrasing: a word that ends a line (punctuation in the lyric) on a held note
gives its last BREATH_S back as a breath, so the singer breathes where a
singer would and the beat doesn't move; sing_parts.py splits phrases there.

Writes {lang, parts: {part: [[midi|null, seconds, word|null, phonemes|null,
type, syllable, syllables]]}}: type 1 rest, 2 a syllable's first note, 3 it
continues; phonemes are espeak IPA for German, SoulX ARPAbet (en_...) for
English. A breath is a rest whose word is "<breath>".
"""
import json, os, re, subprocess, sys  # noqa: E401
from music21 import converter, note as m21note, chord as m21chord, harmony

args = [a for a in sys.argv[1:] if not a.startswith('--')]
opt = {a[2:].split('=')[0]: a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--') and '=' in a}
flags = {a[2:] for a in sys.argv[1:] if a.startswith('--') and '=' not in a}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timing import TempoMap
src, out = args[0], args[1]

if src.endswith('.mxl'):  # compressed MusicXML
    data, score = {}, converter.parse(src)
else:
    raw = open(src, encoding='utf-8').read()
    data = json.loads(raw) if src.endswith('.json') else {'musicxml': raw}
    score = converter.parseData(data['musicxml'], format='musicxml')
TITLE = data.get('title') or (score.metadata.title if score.metadata else None) or os.path.splitext(os.path.basename(src))[0]
COMPOSER = data.get('composer') or (score.metadata.composer if score.metadata else None) or ''
if 'transpose' in opt:  # the whole piece moved, as a choir sings it lower when the top is out of reach
    score = score.transpose(int(opt['transpose']))
names = [p.partName for p in score.parts]
timeline = data.get('timeline')
if not timeline:
    score = score.expandRepeats()
BPM = float(opt.get('bpm') or data.get('bpm') or 72)
GERMAN = re.compile(r"[äöüßÄÖÜ]|\b(und|der|die|das|ich|nicht|mich|uns|mit|sein|ist|dein|mein|herr|gott)\b", re.I)
def language():
    """German or English, from the lyrics (a chorale timeline is German)."""
    if timeline: return 'de'
    words = ' '.join(l.text or '' for n in score.recurse().notes if isinstance(n, m21note.Note) for l in n.lyrics)
    return 'de' if len(GERMAN.findall(words)) >= max(3, len(words.split()) // 20) else 'en'
LANG = opt.get('lang') or language()
BREATH = 0.5
BREATH_S, BREATH_MIN_BEATS = 0.25, 1.5  # a line-end breath, taken from a held note at least this long

def has_lyrics(part):
    return any(isinstance(n, m21note.Note) and n.lyrics for n in part.flatten().notes)
if 'parts' in opt:
    SUNG = opt['parts'].split(',')
elif 'Soprano' in names:
    SUNG = [n for n in ['Soprano', 'Alto', 'Tenor', 'Bass'] if n in names]
else:
    SUNG = [p.partName for p in score.parts if has_lyrics(p)]
TEXT = opt.get('text') or (SUNG[0] if 'Soprano' not in SUNG else 'Soprano')

def score_events(part):
    out = []
    for n in part.flatten().stripTies().notesAndRests:
        if isinstance(n, harmony.ChordSymbol): continue
        if isinstance(n, m21chord.Chord): n = n.notes[-1]
        lyrics = {(l.number or 1): (l.text, l.syllabic) for l in n.lyrics} if isinstance(n, m21note.Note) else {}
        out.append((float(n.offset), float(n.quarterLength), n.pitch.midi if isinstance(n, m21note.Note) else None,
                    lyrics, any(e.classes[0] == 'Fermata' for e in n.expressions)))
    return out

def performed(evs):
    """In playback order: the data's timeline ([play, score, length] per bar),
    each bar's text line chosen by how many times it has been played."""
    if not timeline:
        return [(off, beats, midi, *(lyrics.get(1) or (lyrics[min(lyrics)] if lyrics else (None, None))), ferm)
                for off, beats, midi, lyrics, ferm in evs]
    out, seen = [], {}
    for k, (play, start, length) in enumerate(timeline):
        passes = seen[start] = seen.get(start, 0) + 1
        nxt = timeline[k + 1] if k + 1 < len(timeline) else None
        flows_on = nxt is not None and abs(nxt[1] - (start + length)) < 1e-6
        for off, beats, midi, lyrics, ferm in evs:
            if not (start - 1e-6 <= off < start + length - 1e-6): continue
            if off + beats > start + length + 1e-6 and not flows_on: beats = start + length - off
            text, syl = lyrics.get(passes) or (lyrics[max(lyrics)] if lyrics else (None, None))
            out.append((play + off - start, beats, midi, text, syl, ferm))
    return out

parts = {p.partName: performed(score_events(p)) for p in score.parts if p.partName in SUNG}

# --stop=<bar>.<beat>: everyone ends together there (bars counted as
# performed, repeats taken), on whatever they're singing at that beat, held as
# a fermata: how a canon that goes round "until the end" is brought to a close
if 'stop' in opt:
    bar, beat = (opt['stop'].split('.') + ['1'])[:2]
    measures = list(score.parts[0].getElementsByClass('Measure'))
    m = measures[int(bar) - 1]
    beat_q = (m.timeSignature or score.parts[0].recurse().getElementsByClass('TimeSignature').first()).beatDuration.quarterLength
    stop_q = float(m.offset) + (int(beat) - 1) * beat_q
    for name, evs in parts.items():
        kept = []
        for off, beats, midi, text, syl, ferm in evs:
            if off < stop_q - 1e-6:
                kept.append((off, min(beats, stop_q - off), midi, text, syl, ferm))
            elif abs(off - stop_q) < 1e-6 and midi is not None:
                kept.append((off, beat_q, midi, text, syl, True))   # the last chord, a fermata
        parts[name] = kept

# The song's own pronunciations, before any dictionary
SAY = {}
say_file = re.sub(r'\.(json|xml|musicxml|mxl)$', '', src) + '.say'
try:
    for line in open(say_file, encoding='utf-8'):
        if '=' in line and not line.lstrip().startswith('#'):
            w, ph = line.split('=', 1)
            SAY[w.strip().lower()] = 'en_' + '-'.join(ph.split())
except FileNotFoundError:
    pass
to_check = {}  # word -> why it needs an ear

_cmu = _g2p = None
def phonemes(word: str) -> str:
    """German: espeak-ng IPA. English: the song's .say file, then CMUdict, then g2p_en."""
    global _cmu, _g2p
    if LANG != 'de' and word.lower() in SAY:
        return SAY[word.lower()]
    if LANG == 'de':
        r = subprocess.run(['espeak-ng', '-v', 'de', '-q', '--ipa', word], capture_output=True, text=True).stdout
        return re.sub(r'\s', '', r)
    if _cmu is None:
        import nltk
        try: _cmu = nltk.corpus.cmudict.dict()
        except LookupError: nltk.download('cmudict', quiet=True); _cmu = nltk.corpus.cmudict.dict()
    w = word.lower()
    for key in (w, w.rstrip("'") + 'g' if w.endswith("in'") else None):
        if key and key in _cmu:
            prons = _cmu[key]
            # A real homograph (bass, wind, lead): same length, stressed vowels differ
            alts = [p for p in prons[1:] if len(p) == len(prons[0]) and any(
                x != y and x[-1] == '1' and y[-1] == '1' for x, y in zip(prons[0], p))]
            if alts:
                to_check[w] = 'means? ' + ' | '.join(' '.join(p) for p in [prons[0], *alts]) + '  (using the first)'
            return 'en_' + '-'.join(prons[0])
    if _g2p is None:
        from g2p_en import G2p
        _g2p = G2p()
    guess = [p for p in _g2p(w) if re.match(r'^[A-Z]+\d?$', p)]
    to_check[w] = 'guessed: ' + ' '.join(guess)
    return 'en_' + '-'.join(guess)

def lyric_of(evs):
    """A part's words: each syllable onset -> word id and which syllable it is,
    and which words end a line of the lyric"""
    word_at, syl_at, words, cur, line_ends = {}, {}, [], [], set()
    def flush():
        if not cur: return
        text = ''.join(t for _, t in cur)
        clean = re.sub(r"[^\wäöüÄÖÜß']", '', text)
        if re.search(r"[,.;:!?]['\"’”)]*$", text): line_ends.add(len(words))
        words.append((clean, phonemes(clean), len(cur)))
        for k, (off, _) in enumerate(cur):
            word_at[off] = len(words) - 1
            syl_at[off] = k
        cur.clear()
    for off, beats, midi, text, syl, ferm in evs:
        if midi is None or text is None: continue
        cur.append((off, text.strip()))
        if syl in (None, 'single', 'end'): flush()
    flush()
    return words, word_at, syl_at, line_ends, sorted(word_at)

# A chorale lays the text part's words on every part; a cast each sings their own
OWN = 'text' not in opt and 'Soprano' not in SUNG and len(SUNG) > 1
words, word_at, syl_at, line_ends, onsets = lyric_of(parts[TEXT])
breaths = sorted({off + beats for off, beats, midi, *_, ferm in parts[TEXT] if ferm})
sec = 60 / BPM
ts = score.parts[0].flatten().getElementsByClass('TimeSignature').first()
bar_q = ts.barDuration.quarterLength if ts else 4.0
total_q = max((off + beats for evs in parts.values() for off, beats, *_ in evs), default=0.0)
# The intro's bars start at the first bar line on or after the first sung note
first_sung = min((off for evs in parts.values() for off, _, midi, *_ in evs if midi is not None), default=0.0)
bar_lines = sorted({float(m.offset) for m in score.parts[0].getElementsByClass('Measure')} | {total_q})
entry_q = next(b for b in bar_lines if b >= first_sung - 1e-6)
fermatas = sorted({(off, off + beats) for off, beats, midi, *_, ferm in parts[TEXT] if ferm and midi is not None})
interpret = fermatas and not ({'literal', 'rubato'} & flags)
tm = TempoMap(BPM, bar_q, total_q, int(opt.get('intro', 0)), 'rubato' in flags,
              {b: BREATH * sec for b in breaths}, entry_q, 'swing' in flags, fermatas if interpret else None)
# The phrases, in seconds: each runs from its first note (after the breath
# that ends the one before) to the end of its fermata
phrase_ends = [b for _, b in fermatas] or [total_q]
if phrase_ends[-1] < total_q - 1e-6: phrase_ends.append(total_q)
phrases, begin = [], first_sung
for b in phrase_ends:
    phrases.append([round(tm.start(begin), 3), round(tm.end(b), 3)])
    begin = b

result = {}
for pname, evs in parts.items():
    if OWN: words, word_at, syl_at, line_ends, onsets = lyric_of(evs)
    notes, pending, last = [], list(breaths), None  # last: (word id, syllable) being sung
    wid = {}  # row -> word id
    if tm.intro_s: notes.append([None, tm.intro_s, None, None, 1, None, None])  # the accompaniment's intro
    def note(midi, secs, w, k, kind):
        wid[len(notes)] = w
        return [midi, secs, words[w][0], words[w][1], kind, k, words[w][2]]
    for off, beats, midi, *_ in evs:
        while pending and pending[0] <= off + 1e-6:
            notes.append([None, tm.holds[pending[0]], None, None, 1, None, None]); pending.pop(0); last = None
        if midi is None:
            notes.append([None, tm.end(off + beats) - tm.start(off), None, None, 1, None, None]); last = None; continue
        cuts = [off] + [o for o in onsets if off + 1e-6 < o < off + beats - 1e-6] + [off + beats]
        for a, b in zip(cuts, cuts[1:]):
            w = word_at.get(a)
            if w is not None and (w, syl_at[a]) != last:
                last = (w, syl_at[a])
                notes.append(note(midi, tm.end(b) - tm.start(a), w, last[1], 2))
            elif last is not None:
                notes.append(note(midi, tm.end(b) - tm.start(a), last[0], last[1], 3))
            else:
                # No syllable yet after a rest: a part coming in while the text
                # part's next syllable starts takes it early; otherwise it rests
                nxt = next((o for o in onsets if o >= a), None)
                if nxt is not None and nxt < b - 1e-6:
                    last = (word_at[nxt], syl_at[nxt])
                    notes.append(note(midi, tm.end(b) - tm.start(a), last[0], last[1], 2))
                else:
                    notes.append([None, tm.end(b) - tm.start(a), None, None, 1, None, None])
    # Breaths at line ends: the word's last note, held, gives up its tail
    sec_beat = 60 / BPM
    for i in range(len(notes) - 1, -1, -1):
        row = notes[i]
        if row[0] is None or wid[i] not in line_ends: continue
        if i + 1 < len(notes) and wid.get(i + 1) == wid[i]: continue  # not the word's last note
        if row[1] < BREATH_MIN_BEATS * sec_beat: continue
        if i + 1 < len(notes) and notes[i + 1][0] is None: continue  # a rest follows already
        if all(r[0] is None for r in notes[i + 1:]): continue  # the last note: nothing to breathe for
        take = min(BREATH_S, row[1] * 0.3)
        row[1] -= take
        notes.insert(i + 1, [None, take, '<breath>', None, 1, None, None])
    result[pname] = notes
json.dump({'title': TITLE, 'composer': COMPOSER, 'bpm': BPM, 'lang': LANG, 'timing': tm.to_json(), 'phrases': phrases, 'parts': result},
          open(out, 'w'), ensure_ascii=False, indent=1)
print(out, LANG, f'{BPM:g} bpm', {p: len(n) for p, n in result.items()}, len(words), 'words')
if to_check:
    print(f'Check these (fix in {os.path.basename(say_file)}):')
    for w, why in sorted(to_check.items()): print(f'  {w}: {why}')
