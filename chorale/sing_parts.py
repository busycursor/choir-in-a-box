"""Sing parts (from score_parts.py) with SoulX-Singer, one voice prompt per
part. English arrives as ARPAbet. German has no phonemes of its own in
SoulX, so each syllable is spelled in English ARPAbet from espeak-ng's German
IPA (stress kept): the closest sounds a careful English speaker would use. Each syllable is pinned to the
note it starts on, and each part is rendered as phrases split at its rests and
breaths (score_parts.py's line ends; a word every 12s only if a line runs on
that long), each placed at its exact time, so nothing drifts and SoulX never
gets a long silence to fill.

Usage (from the repo root):
  engine/soulx/.venv/bin/python chorale/sing_parts.py <parts.json> <out dir> Part=<prompt dir>[:shift] ... [--steps=64]
A prompt dir holds prompt.wav + prompt.json (see prompt.py); shift moves that
part's notes by semitones (0 = as written). Writes <out dir>/<part>.wav and,
for several parts, <out dir>/mix.wav. --steps sets SoulX's refinement steps
(its config says 32; 64 is cleaner and slower); --cfg how strongly it follows
the prompt and the score (its config says 3; higher holds the voice and the
notes closer, at the risk of a harsher sound). --ghost=0 and --cons-lead=0
turn off the running start and the consonants-before-the-beat, to try a hard
line several ways.
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine', 'soulx')  # the SoulX checkout, venv and model

# German IPA -> ARPAbet, longest match first; vowels take stress, set by ˈ/ˌ
VOWELS = [('aɪ', 'AY'), ('aʊ', 'AW'), ('ɔʏ', 'OY'), ('ɔø', 'OY'), ('ɔy', 'OY'),
          ('aː', 'AA'), ('a', 'AA'), ('ɛː', 'EH'), ('ɛ', 'EH'), ('eː', 'EY'), ('e', 'EY'),
          ('iː', 'IY'), ('i', 'IY'), ('ɪ', 'IH'), ('oː', 'OW'), ('o', 'OW'), ('ɔ', 'AO'),
          ('uː', 'UW'), ('u', 'UW'), ('ʊ', 'UH'), ('øː', 'EY'), ('ø', 'EY'), ('œ', 'EH'),
          ('yː', 'IY'), ('y', 'IY'), ('ʏ', 'IH'), ('ə', 'AH'), ('ɐ', 'AH'), ('ɜ', 'AH')]
CONS = [('tʃ', 'CH'), ('dʒ', 'JH'), ('ts', 'T S'), ('pf', 'P F'), ('ç', 'SH'), ('x', 'HH'),
        ('ʁ', 'R'), ('ɾ', 'R'), ('r', 'R'), ('ʀ', 'R'), ('ŋ', 'NG'), ('ʃ', 'SH'), ('ʒ', 'ZH'),
        ('b', 'B'), ('d', 'D'), ('ɡ', 'G'), ('g', 'G'), ('p', 'P'), ('t', 'T'), ('k', 'K'),
        ('f', 'F'), ('v', 'V'), ('s', 'S'), ('z', 'Z'), ('h', 'HH'), ('j', 'Y'),
        ('l', 'L'), ('m', 'M'), ('n', 'N'), ('ʔ', '')]

def arpabet(ipa: str) -> str:
    out, i, stress = [], 0, None
    while i < len(ipa):
        c = ipa[i]
        if c == 'ˈ': stress = '1'; i += 1; continue
        if c == 'ˌ': stress = '2'; i += 1; continue
        for src, dst in VOWELS:
            if ipa.startswith(src, i):
                out.append(dst + ('0' if dst == 'AH' else (stress or '0'))); stress = None; i += len(src); break
        else:
            for src, dst in CONS:
                if ipa.startswith(src, i):
                    out += dst.split(); i += len(src); break
            else:
                i += 1
    return 'en_' + '-'.join(out)

PAD = 0.15        # silence after each phrase
RUN_UP = 0.4      # silence before each phrase: SoulX sometimes bursts in the first frames it generates
                  # (the hand-over from the voice prompt), so the singing starts well after them
SPLIT_REST = 0.4  # a rest at least this long ends a phrase
PICKUP, PICKUP_HEAD = 0.4, 0.5  # a segment opening on a note shorter than PICKUP gets up to PICKUP_HEAD of lead-in
GHOST = 0.3  # ...in which it sings a muted copy of that note first
CONS_S, MAX_LEAD = 0.05, 0.12  # each opening consonant starts this much before its note, at most MAX_LEAD
LEAD_IN = 0.5  # the score starts this far into the audio, so a part opening on the first beat gets its lead-in too
MAX_PHRASE = 12.0  # a longer phrase splits at the next word, pinned there too (a seam: a last resort)

def syllable_phonemes(ipa: str, k: int, n: int) -> str:
    """Syllable k of n of a word, as SoulX phonemes: the word's ARPAbet dealt out
    one vowel per syllable, the last consonant between two vowels starting the
    next (a word whose vowel count differs has its vowels spread evenly)."""
    phs = (ipa if ipa.startswith('en_') else arpabet(ipa))[3:].split('-')  # English arrives as ARPAbet already
    if n <= 1: return 'en_' + '-'.join(phs)
    vi = [i for i, p in enumerate(phs) if p[-1].isdigit()]
    if len(vi) != n:
        vi = [vi[round(j * (len(vi) - 1) / (n - 1))] for j in range(n)] if vi else list(range(n))
    cuts = [0] + [vi[j] - (1 if vi[j] - vi[j - 1] > 1 else 0) for j in range(1, n)] + [len(phs)]
    part = phs[cuts[k]:cuts[k + 1]] or phs[vi[min(k, len(vi) - 1)]:vi[min(k, len(vi) - 1)] + 1]
    return 'en_' + '-'.join(part)

def target(notes, shift):
    """The part as phrases split at its rests, each a segment pinned to its own
    start time: SoulX places every segment exactly, so timing can't drift
    across the piece and it never gets a long silence to fill."""
    # A phrase can't begin before the audio does: one opening at 0:00 had its
    # start clamped there, which put the whole first phrase 150 ms late
    segments, phrase, t, start = [], [], LEAD_IN, None
    head = RUN_UP  # lead-in of the phrase being built
    def close(tail=PAD):
        nonlocal head, start
        if not phrase: return
        # Consonants before the beat: a syllable's opening consonants start a
        # little before its note, taken from the end of the note (or rest)
        # before, so the vowel lands on the beat. Pinned at the note's start,
        # they pushed the vowel late ("it has" came out "it-hzzz", a beat behind)
        for i, (text, ph, secs, pitch, kind) in enumerate(phrase):
            if kind != 2: continue
            cons = 0
            for p in ph[3:].split('-'):
                if p[-1:].isdigit() or p == '<SP>': break
                cons += 1
            if not cons: continue
            if i == 0:
                lead_s = min(CONS_S * cons, MAX_LEAD, max(0.0, head - 0.05))
                head -= lead_s; start -= lead_s
            else:
                prev = phrase[i - 1]
                lead_s = min(CONS_S * cons, MAX_LEAD, prev[2] * (1.0 if prev[0] == '<SP>' else 0.4))
                phrase[i - 1] = (*prev[:2], prev[2] - lead_s, *prev[3:])
            phrase[i] = (text, ph, secs + lead_s, pitch, kind)
        lead = [('<SP>', '<SP>', head, 0, 1)]
        # A phrase opening cold on a quick pickup gets a running start: a muted
        # copy of its first syllable sung first (the runner cuts it), so the
        # voice and pitch are already going when the real note comes
        ghost = GHOST > 0 and phrase[0][2] < PICKUP and head >= GHOST + 0.1
        if ghost:
            text, ph, _, pitch, _ = phrase[0]
            lead = [('<SP>', '<SP>', head - GHOST, 0, 1), (text, ph, GHOST, pitch, 2)]
        rows = lead + phrase + ([('<SP>', '<SP>', tail, 0, 1)] if tail else [])
        begin = max(0.0, start - head)
        sung = sum(r[2] for r in phrase)
        segments.append({'index': f'phrase_{len(segments)}', 'language': 'English',
                         'time': [int(round(begin * 1000)), int(round((begin + sum(r[2] for r in rows)) * 1000))],
                         'content': [int(round(start * 1000)), int(round((start + sung) * 1000))],  # the notes, without padding
                         'duration': ' '.join(f'{r[2]:.3f}' for r in rows), 'text': ' '.join(r[0] for r in rows),
                         'phoneme': ' '.join(r[1] for r in rows), 'note_pitch': ' '.join(str(int(r[3])) for r in rows),
                         'note_type': ' '.join(str(r[4]) for r in rows), **({'ghost': True} if ghost else {})})
        phrase.clear()
    # Rests next to each other (a bar line splits one) count as one
    merged = []
    for row in notes:
        if row[0] is None and merged and merged[-1][0] is None and '<breath>' not in (row[2], merged[-1][2]):
            merged[-1] = [None, merged[-1][1] + row[1], None, None, 1, None, None]
        else:
            merged.append(list(row))
    for i, (midi, secs, word, ipa, kind, syl, nsyl) in enumerate(merged):
        if midi is None:
            if word == '<breath>' or secs >= SPLIT_REST:
                close()
                # A segment opening on a quick pickup gets more of the rest as its
                # lead-in: with only PAD, SoulX swallows or mis-pitches the short note
                nxt = merged[i + 1] if i + 1 < len(merged) else None
                head = PICKUP_HEAD if nxt and nxt[0] is not None and nxt[1] < PICKUP else RUN_UP  # may reach back into the phrase before: the runner mixes the overlap
            elif phrase: phrase.append(('<SP>', '<SP>', secs, 0, 1))
        else:
            if phrase and kind == 2 and not syl and t - start >= MAX_PHRASE:  # only at a word's start
                close()  # padded like a rest split: the runner mixes the overlap, so nothing cuts off
                head = RUN_UP
            if not phrase:
                start = t
                if kind == 3: kind = 2  # a phrase can't open mid-word
            # each syllable its own sounds, pinned to the note Bach put it on
            text = word if (nsyl or 1) <= 1 else f'{word}{syl + 1}'
            phrase.append((text, syllable_phonemes(ipa, syl or 0, nsyl or 1), secs, midi + shift, kind))
        t += secs
    close()
    return segments

JITTER_MS = 20  # each further singer in a section starts each phrase up to this much early or late

def jittered(segments, part, k):
    """Singer k's copy of a section's phrases: the first singer as written, each
    other one moved by a seeded ±JITTER_MS per phrase, as section singers
    never land exactly together."""
    if k == 0: return segments
    rng = np.random.default_rng([ord(c) for c in part] + [k])  # seeded: a re-render is identical
    out = []
    for seg in segments:
        d = int(rng.uniform(-JITTER_MS, JITTER_MS))
        d = max(d, -seg['time'][0])
        seg = {**seg, 'time': [seg['time'][0] + d, seg['time'][1] + d]}
        if 'content' in seg: seg['content'] = [seg['content'][0] + d, seg['content'][1] + d]
        out.append(seg)
    return out

def section(wavs):
    """Several singers' takes of one part, summed and brought back to a single
    singer's loudness, so a section and a soloist balance alike."""
    n = max(len(w) for w in wavs)
    total = sum(np.pad(w, (0, n - len(w))) for w in wavs)
    rms = lambda x: np.sqrt(np.mean(x ** 2)) or 1e-9
    return total * (np.mean([rms(w) for w in wavs]) / rms(total))

if __name__ == '__main__':
    steps = next((int(a.split('=')[1]) for a in sys.argv[3:] if a.startswith('--steps=')), None)
    cfg = next((float(a.split('=')[1]) for a in sys.argv[3:] if a.startswith('--cfg=')), None)
    # Switches for trying a hard line several ways: --ghost=0 (no running
    # start), --cons-lead=0 (consonants on the beat, as before)
    for a in sys.argv[3:]:
        if a.startswith('--ghost='): GHOST = float(a.split('=')[1])
        if a.startswith('--cons-lead='): CONS_S = float(a.split('=')[1])
    parts_json, out_dir, specs = sys.argv[1], sys.argv[2], [a for a in sys.argv[3:] if not a.startswith('--')]
    data = json.load(open(parts_json))
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    jobs, outs = [], []
    for spec in specs:  # Part=<prompt dir>[:shift], or a section: Part=<dir>[:shift],<dir>[:shift],...
        part, rest = spec.split('=')
        singers = []
        for k, one in enumerate(rest.split(',')):
            prompt, shift = (one.split(':') + ['0'])[:2]
            prompt = os.path.abspath(prompt)
            name = part.lower() if k == 0 and ',' not in rest else f'{part.lower()}-{k + 1}'
            t = os.path.join(out_dir, f'{name}-target.json')
            json.dump(jittered(target(data['parts'][part], int(shift)), part, k), open(t, 'w'), ensure_ascii=False)
            out = os.path.join(out_dir, f'{name}.wav')
            jobs.append({'prompt_wav': os.path.join(prompt, 'prompt.wav'), 'prompt_meta': os.path.join(prompt, 'prompt.json'),
                         'target_meta': t, 'out': out, **({'n_steps': steps} if steps else {}), **({'cfg': cfg} if cfg else {}),
                         **({'section': part} if ',' in rest else {})})
            singers.append(out)
        outs.append((part, os.path.join(out_dir, f'{part.lower()}.wav'), singers))
    jobs_path = os.path.join(out_dir, 'jobs.json')
    json.dump(jobs, open(jobs_path, 'w'))
    # One run for every part: our runner (soulx_render.py) mixes segments rather than pasting them
    subprocess.run([os.path.join(ENGINE, '.venv/bin/python'), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'soulx_render.py'), jobs_path],
                   cwd=ENGINE, env={**os.environ, 'PYTHONPATH': ENGINE, 'PYTORCH_ENABLE_MPS_FALLBACK': '1'},
                   check=True, stderr=subprocess.DEVNULL)  # stdout: each part as it lands, and any octave slip sung again
    mixed = None
    for part, out, singers in outs:
        if len(singers) > 1:
            takes = [sf.read(w) for w in singers]
            sr = takes[0][1]
            sf.write(out, section([w for w, _ in takes]), sr)
        wav, sr = sf.read(out)
        print(part, f'{len(wav) / sr:.1f}s')
        if mixed is None: mixed = wav
        else:
            n = max(len(mixed), len(wav))
            mixed = np.pad(mixed, (0, n - len(mixed))) + np.pad(wav, (0, n - len(wav)))
    if len(outs) > 1:
        sf.write(os.path.join(out_dir, 'mix.wav'), mixed / max(1e-6, np.abs(mixed).max()) * 0.9, sr)
