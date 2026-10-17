"""Our SoulX-Singer runner: the model loaded once for every part, and each
part's segments mixed rather than pasted. SoulX's own CLI writes each
segment over the one before, so a segment starting a little early cuts the
last note of the one before it off; here each segment fades in and out over
a few milliseconds and overlapping audio adds. A phrase given a running start
(sing_parts.py: a muted copy of a quick first note) is cut back to its real
first note the same way. Where a phrase was split
mid-line, the next one starting before this one's padding ends, this one
releases over 50 ms from its last note's end and the next fades in just
before its first note, so a held-over tail doesn't sound as a second note.
Every other phrase is silent until just before its first consonant. At the
hand-over from the voice prompt, SoulX sometimes jumps the gun and starts the
first sound at once, ignoring the silence it was given (f8's alto sang a faint
"v" of "Wär'" there, then a gap, then the phrase on time). sing_parts.py
leaves RUN_UP of silence before each phrase so that early start lands well
clear of the singing, and this drops it.

Run by sing_parts.py with the engine as the working directory:
  python soulx_render.py <jobs.json>
jobs.json: [{"prompt_wav", "prompt_meta", "target_meta", "out", "n_steps"?, "cfg"?, "seed"?, "gate"?, "tries"?}, ...]
("seed" offsets every phrase's seed; "gate": false leaves the lead-in as sung, to listen to;
"tries": 1 keeps the first take even if it slips; "section": the part, for a singer in
a section, who sits out a phrase that still slips rather than singing it wrong, unless the
whole section would: then one of them keeps their third take)
"""
import json, sys
import numpy as np
import soundfile as sf
import torch
from cli.inference import build_model
from soulxsinger.utils.file_utils import load_config
from soulxsinger.utils.data_processor import DataProcessor
import pitchcheck  # next to this script

FADE_S = 0.02
TRIES = 3          # sings of a phrase before an octave slip is kept
RELEASE_S = 0.05   # a split phrase's release after its last note
ONSET_S = (0.08, 0.02)  # the next phrase fades in over this window before its first note
LEAD_GATE_S = (0.04, 0.01)  # any other phrase: silent until 40 ms before its first consonant, faded in by 10 ms before
CONFIG = 'soulxsinger/config/soulxsinger.yaml'
MODEL = 'pretrained_models/SoulX-Singer/model.pt'
PHONESET = 'soulxsinger/utils/phoneme/phone_set.json'

def main(jobs_path):
    jobs = json.load(open(jobs_path))
    device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    config = load_config(CONFIG)
    model = build_model(model_path=MODEL, config=config, device=device)
    sr = config.audio.sample_rate
    processor = DataProcessor(hop_size=config.audio.hop_size, sample_rate=sr, phoneset_path=PHONESET, device=device)
    fade = int(FADE_S * sr)
    held = {}   # (section, phrase) -> [(out file, start sample, audio)]: left out, in case the whole section left it out
    for job in jobs:
        prompt = processor.process(json.load(open(job['prompt_meta']))[0], job['prompt_wav'])
        segments = json.load(open(job['target_meta']))
        merged = np.zeros(int(max(s['time'][1] for s in segments) / 1000 * sr) + sr, dtype=np.float32)
        for i, seg in enumerate(segments):
            start = int(seg['time'][0] / 1000 * sr)
            for attempt in range(job.get('tries', TRIES)):  # a phrase with a note an octave off is sung again (pitchcheck.py)
                torch.manual_seed(job.get('seed', 0) + 1000 * i + attempt)  # seeded, so a re-render is identical
                with torch.no_grad():
                    audio = model.infer({'prompt': prompt, 'target': processor.process(json.loads(json.dumps(seg)), None)},  # it rewrites what it's given
                                        auto_shift=False, pitch_shift=0, n_steps=job.get('n_steps', config.infer.n_steps),
                                        cfg=job.get('cfg', config.infer.cfg), control='melody' if 'f0' in seg else 'score', use_fp16=False)
                audio = audio.squeeze().cpu().numpy().astype(np.float32)
                off = [] if 'f0' in seg else pitchcheck.slips(audio, sr, seg)   # sung to a pitch curve: it goes where it's told
                if not off: break
                last = attempt + 1 == job.get('tries', TRIES)
                print(f'{job["out"]} phrase {i}: {", ".join(off)}' + ('; again' if not last else
                      ('; left out (the section carries it)' if job.get('section') else '; kept')), flush=True)
            n = min(len(audio), len(merged) - start)
            audio = audio[:n]
            ramp = np.linspace(0, 1, min(fade, n // 2), dtype=np.float32)
            audio[:len(ramp)] *= ramp
            audio[n - len(ramp):] *= ramp[::-1]
            if 'content' in seg:
                prev, nxt = (segments[i - 1] if i else None), (segments[i + 1] if i + 1 < len(segments) else None)
                joined = seg.get('ghost') or (prev and prev['time'][1] > seg['time'][0])  # split from the phrase before, or a running start to cut
                if joined or job.get('gate', True):
                    gate = ONSET_S if joined else LEAD_GATE_S
                    a = int((seg['content'][0] / 1000 - gate[0]) * sr) - start
                    b = int((seg['content'][0] / 1000 - gate[1]) * sr) - start
                    a, b = max(0, a), max(0, min(n, b))
                    audio[:a] = 0
                    audio[a:b] *= np.linspace(0, 1, b - a, dtype=np.float32)
                if nxt and nxt['time'][0] < seg['time'][1]:  # split from the phrase after
                    a = max(0, min(n, int(seg['content'][1] / 1000 * sr) - start))
                    b = min(n, a + int(RELEASE_S * sr))
                    audio[a:b] *= np.linspace(1, 0, b - a, dtype=np.float32)
                    audio[b:] = 0
            if off and job.get('section'):   # a section singer who can't get it right sits this phrase out
                held.setdefault((job['section'], i), []).append((job['out'], start, audio))
                continue
            merged[start:start + n] += audio
        end = len(merged)
        while end > 0 and abs(merged[end - 1]) < 1e-5: end -= 1
        sf.write(job['out'], merged[:end], sr)
        print(job['out'], f'{end / sr:.1f}s', flush=True)
    # A phrase the whole section left out would leave the part silent: one
    # singer's third take goes back in instead, as a soloist's would
    singers = {}
    for job in jobs:
        if job.get('section'):
            singers[job['section']] = singers.get(job['section'], 0) + 1
    for (section, i), takes in held.items():
        if len(takes) < singers[section]:
            continue
        out, start, audio = takes[0]
        merged, _ = sf.read(out, dtype='float32')
        if len(merged) < start + len(audio):
            merged = np.pad(merged, (0, start + len(audio) - len(merged)))
        merged[start:start + len(audio)] += audio
        sf.write(out, merged, sr)
        print(f'{out} phrase {i}: the whole section left it out; kept this third take', flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
