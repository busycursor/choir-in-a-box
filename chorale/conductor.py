"""The conductor: a line spoken before a piece by the ElevenLabs voice named
"Conductor" (an erudite, slightly awkward choral conductor), with delivery
cues in brackets, and how he's heard. He isn't a professional speaker and has
no microphone of his own: he stands up by the choir, so he reaches the
recording through the church, and as he talks he wanders and turns away and
back, so his level and brightness keep shifting.

Usage: ELEVENLABS_API_KEY=... python -m chorale.conductor ["[a cue] the line"] [--takes=3]
(the line defaults to LINE, the cue to CUE)
writes engine/audience/conductor/<line>_<take>.mp3 to listen to; picks go in audience/picks.json under "conductor".
"""
import hashlib, json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LINES = ROOT / 'engine' / 'audience' / 'conductor'
VOICE = 'Conductor'
MODEL, STABILITY = 'eleven_v4', 0.45  # low enough for the cues to come through; lower, he improvises on the words
# How he speaks unless a line says otherwise. Found by ear: "diffidently" came
# out timid, "eager" overdone, "declamatory" a radio voice, and most cues
# rose at the end; this one is a person addressing a hall, ending on a period.
# Writing his lines: to sound off the cuff rather than read, give him one small
# stutter on a short word, written in ("dedicated to-to my"). Not "um" (too
# much), not a repeated phrase ("this next... this next" came back three
# times at 0.3 stability: he improvised on the pattern), not an inserted pause.
# Capitals mark the stress he'd give it ("Good EVENING.").
CUE = '[announcing to the assembled crowd with very slight reluctance]'
SPEED = 1.08   # his takes come back a touch slow for someone itching to start: sped up, same pitch
LINE = 'I hope you enjoy this next chorale.'


def cued(text: str) -> str:
    return text if text.lstrip().startswith('[') else f'{CUE} {text}'

SR = 24000

# Where he stands and how he moves (room.Seat terms: pan -1..1, distance 0..1)
STAND = (0.05, 0.5)          # front and centre, by the choir, back from the recording
WANDER_PAN = 0.18            # how far he drifts either side over a long speech
TURN_DB, TURN_DULL_DB = 4.0, 3.0   # turned away: this much quieter, and this much less top end
TURN_EVERY = 4.5             # seconds of talking per turn away and back: a short line has time for one at most
TURN_LENGTH = (1.2, 3.5)     # seconds a turn takes, drawn per turn, never more than half the line


def _key() -> str:
    return os.environ['ELEVENLABS_API_KEY']


# The brief the Conductor was designed from (ElevenLabs Voice Design). A
# designed voice can't be shared outside its account, so another account gets
# its own Conductor designed from the same brief: the same idea, not the same voice.
DESCRIPTION = ('An erudite tenor voice, the conductor of an orchestra or choral ensemble, smart, clipped, almost '
               'trans-atlantic, but still warm and friendly. Used to introduce pieces, to explain music history, and to '
               'speak to the choir or orchestra. Capable of great emotion, but generally declamatory. Studio quality '
               'with no echoes or artifacts.')


def _api(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request('https://api.elevenlabs.io' + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'xi-api-key': _key(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def voice_id(name: str = VOICE) -> str:
    """The Conductor's voice: CONDUCTOR_VOICE_ID if set, else the account's voice
    named Conductor, else one designed from DESCRIPTION and saved under that name."""
    if os.environ.get('CONDUCTOR_VOICE_ID'):
        return os.environ['CONDUCTOR_VOICE_ID']
    voices = _api(f'/v2/voices?search={urllib.parse.quote(name)}&page_size=20')['voices']
    match = [v for v in voices if v['name'] == name]
    if match:
        return match[0]['voice_id']
    design = _api('/v1/text-to-voice/design', {'voice_description': DESCRIPTION, 'model_id': 'eleven_ttv_v3', 'auto_generate_text': True})
    made = _api('/v1/text-to-voice', {'voice_name': name, 'voice_description': DESCRIPTION,
                                      'generated_voice_id': design['previews'][0]['generated_voice_id']})
    print(f'conductor: designed a voice named {name} in your ElevenLabs account from the brief in conductor.py')
    return made['voice_id']


def say(text: str, takes: int = 3) -> list[Path]:
    """Takes of a line (given CUE unless it has its own), skipping any already made."""
    text = cued(text)
    LINES.mkdir(parents=True, exist_ok=True)
    words = re.sub(r'\[[^\]]*\]', '', text)
    slug = re.sub(r'[^a-z0-9]+', '-', words.lower()).strip('-')[:40] + '-' + hashlib.sha1(text.encode()).hexdigest()[:6]
    if STABILITY != 0.3:  # takes made before stability was part of the name were at 0.3
        slug += f'-s{round(STABILITY * 100)}'
    vid, out = None, []
    for t in 'abcdefgh'[:takes]:
        f = LINES / f'{slug}_{t}.mp3'
        out.append(f)
        if f.exists():
            continue
        vid = vid or voice_id()
        req = urllib.request.Request(
            'https://api.elevenlabs.io/v1/text-to-dialogue?output_format=mp3_44100_192',
            data=json.dumps({'inputs': [{'text': text, 'voice_id': vid}], 'model_id': MODEL,
                             'settings': {'stability': STABILITY}}).encode(),
            headers={'xi-api-key': _key(), 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as r:
            f.write_bytes(r.read())
        f.with_suffix('.json').write_text(json.dumps({'text': text}) + '\n')
        print(f.name, flush=True)
    return out


def spoken(take: Path) -> np.ndarray:
    """A take, mono at SR, sped up by SPEED with its pitch kept (ffmpeg's atempo)."""
    import subprocess
    raw = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(take), '-af', f'atempo={SPEED}',
                          '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def staged(voice: np.ndarray, seed: int = 0) -> np.ndarray:
    """His mono line as the recording hears it, before the room: panned where
    he wanders, quieter and duller each time he turns away. (room.place and the
    church's reverb then set him back by the choir.)"""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    n = len(voice)
    t = np.arange(n) / SR
    # turning: as many turns away and back as the line has time for, each its
    # own length and depth (a short line: one gentle one, or none)
    secs = n / SR
    turn = np.zeros(n)
    for _ in range(rng.poisson(secs / TURN_EVERY) if secs > TURN_EVERY else int(rng.random() < secs / TURN_EVERY)):
        length = min(rng.uniform(*TURN_LENGTH), secs / 2)
        at = rng.uniform(0, max(0.0, secs - length))
        depth = rng.uniform(0.3, 1.0) * min(1.0, secs / TURN_EVERY)
        mask = (t >= at) & (t < at + length)
        turn[mask] = np.maximum(turn[mask], depth * np.sin(np.pi * (t[mask] - at) / length) ** 2)
    level = 10 ** (-TURN_DB * turn / 20)
    bright = sosfilt(butter(2, 2500, 'highpass', fs=SR, output='sos'), voice)
    dulled = voice + (10 ** (-TURN_DULL_DB * turn / 20) - 1) * bright
    wander = WANDER_PAN * min(1.0, secs / 8)        # a few words: hardly moving; a speech: across the front
    pan = STAND[0] + wander * np.sin(2 * np.pi * t / rng.uniform(5, 8) + rng.uniform(0, 6)) + 0.03 * np.sin(2 * np.pi * t / 1.7)
    angle = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    x = dulled * level
    return np.stack([np.cos(angle) * x, np.sin(angle) * x], 1)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
    for f in say(args[0] if args else LINE, int(opt.get('takes', 3))):
        print(f)
