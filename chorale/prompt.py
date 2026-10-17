"""SoulX-Singer's voice-prompt format. SoulX sings in the voice of a short
sung clip plus its transcription: each note with its duration, its phonemes
(English ARPAbet with stress, as SoulX spells them) and its pitch.
import_vocalset.py builds every prompt with these.
"""
import re

import nltk

SR, HOP = 24000, 480          # SoulX-Singer's audio: 50 frames a second
FPS = SR / HOP

_cmu = _g2p = None
def arpabet(word: str) -> str:
    """An English word as SoulX writes it: en_ + ARPAbet with stress, dash-joined.
    CMUdict first; g2p_en for words it doesn't have."""
    global _cmu, _g2p
    if _cmu is None:
        try: _cmu = nltk.corpus.cmudict.dict()
        except LookupError:
            nltk.download('cmudict', quiet=True); _cmu = nltk.corpus.cmudict.dict()
    w = re.sub(r"[^a-z']", '', word.lower())
    if w in _cmu: return 'en_' + '-'.join(_cmu[w][0])
    if _g2p is None:
        from g2p_en import G2p
        _g2p = G2p()
    return 'en_' + '-'.join(p for p in _g2p(w) if re.match(r'^[A-Z]+\d?$', p))

def meta(index, notes, f0=None):
    """notes: [(text, phoneme, seconds, midi, type)] (type 1 rest, 2 new syllable, 3 it continues)."""
    total_ms = int(round(sum(n[2] for n in notes) * 1000))
    m = {'index': index, 'language': 'English', 'time': [0, total_ms],
         'duration': ' '.join(f'{n[2]:.3f}' for n in notes),
         'text': ' '.join(n[0] for n in notes), 'phoneme': ' '.join(n[1] for n in notes),
         'note_pitch': ' '.join(str(int(n[3])) for n in notes), 'note_type': ' '.join(str(n[4]) for n in notes)}
    if f0 is not None: m['f0'] = ' '.join(f'{x:.1f}' for x in f0)
    return [m]
