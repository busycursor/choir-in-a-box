"""A live audience under a church render (--audience): the room's own quiet
air; before the first note the choir walking on, stepping up onto the risers
and settling, and the listeners settling with them; during the music now and
then one small sound far back in a longer break between phrases; and applause
once the last chord has rung away. It has to suggest a performance, not a
ward: around the music the hall is audibly alive, during it nearly silent,
every sound distant and soft, most breaks left empty, and nothing landing
while anyone is singing.

The sounds are ElevenLabs sound effects, made as takes to listen to
(generate: engine/audience/takes/, with a page to audition them); only the
ones picked by ear are used, kept in assets/audience/ as <kind>_a.mp3,
<kind>_b.mp3 and so on (keep copies a pick there). The room's air is
synthesized instead: ElevenLabs room tones come back near-silent with codec
noise.

Usage:
  ELEVENLABS_API_KEY=... python -m chorale.audience generate [--more=<kind>]
  python -m chorale.audience keep <kind> <take letter>...   (e.g. keep cough b e)
  python -m chorale.audience picks          (lists what's kept)
"""
import json, os, sys, urllib.request
from pathlib import Path

import librosa
import numpy as np
import pyloudnorm

ROOT = Path(__file__).resolve().parent.parent
TAKES = ROOT / 'engine' / 'audience' / 'takes'
KEPT = ROOT / 'assets' / 'audience'
CONDUCTOR = ROOT / 'assets' / 'conductor'

# Each a sound effect, not a performance: the material and the action, where
# it's heard from, and no voices or music (a first set naming the choir and
# the concert came back as singing). Generic: nothing about the project.
WHERE = 'distant, in a large reverberant stone church, no voices, no music'
KINDS = {
    'walk_on':  (f'Footsteps of about twenty people walking slowly across a stone floor, {WHERE}', 6.0, 3),
    'risers':   (f'People stepping up onto hollow wooden risers, soft creaks and shuffling footsteps, then still, {WHERE}', 5.0, 3),
    'folders':  (f'Fabric rustling and stiff paper folders opening, a group of people standing in place, {WHERE}', 3.0, 3),
    'seats':    (f'Wooden pews creaking softly as a few people shift their weight, {WHERE}', 2.5, 3),
    'settle':   (f'Audience ambience before a performance: soft shuffling and wooden pews creaking, then quiet, {WHERE}', 6.0, 3),
    'cough':    (f'One brief, discreet, stifled cough, far away and very soft, one-shot, {WHERE}', 2.0, 4),
    'rustle':   (f'One paper page turning and a soft fabric rustle, one-shot, {WHERE}', 2.0, 4),
    'pew':      (f'One soft wooden creak, one-shot, {WHERE}', 1.5, 3),
    'baton':    (f'A thin wooden conductor\'s baton picked up from a metal music stand, one faint light click, one-shot, {WHERE}', 1.0, 4),
    'score_page': (f'One large page of a bound score turned on a music stand, soft paper, one-shot, {WHERE}', 1.5, 4),
    'stand':    (f'A metal music stand nudged slightly, one faint creak, one-shot, {WHERE}', 1.0, 3),
    'false_start': ('Scattered clapping begins hesitantly from a few people spread across an audience of 150, '
                    'a few more join for a moment, then it stops abruptly and awkwardly into silence, '
                    'distant, in a large reverberant stone church, no voices, no music', 4.0, 4),
    'applause': ('Polite applause from about 150 people, starting gently, sustained, then thinning out to a few last '
                 'scattered claps that stop on their own, distant, in a large reverberant stone church, '
                 'no cheering, no whistles, no voices, no music', 15.0, 4),
}


def _sound(text: str, seconds: float) -> bytes:
    req = urllib.request.Request(
        'https://api.elevenlabs.io/v1/sound-generation',
        data=json.dumps({'text': text, 'duration_seconds': seconds, 'prompt_influence': 0.7,
                         'model_id': 'eleven_text_to_sound_v2'}).encode(),
        headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY'], 'Content-Type': 'application/json',
                 'Accept': 'audio/mpeg'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def generate(more: str | None = None) -> Path:
    """Review takes of every kind not made yet (or four more of one), then a page to audition them."""
    TAKES.mkdir(parents=True, exist_ok=True)
    for kind, (text, seconds, count) in KINDS.items():
        if more and kind != more:
            continue
        have = sorted(f.stem[len(kind) + 1:] for f in TAKES.glob(f'{kind}_?.mp3'))
        if more:
            letters = [c for c in 'abcdefghijklmnop' if c not in have][:4]
        else:
            letters = [] if have else list('abcdefgh'[:count])
        for t in letters:
            f = TAKES / f'{kind}_{t}.mp3'
            if f.exists():
                continue
            print(f.name, flush=True)
            f.write_bytes(_sound(text, seconds))
    rows = []
    approved = set(picks())
    for kind in KINDS:
        if kind in approved:
            continue   # picked already: the page shows only what's still to choose
        files = sorted(TAKES.glob(f'{kind}_*.mp3'))
        rows.append(f'<h2>{kind}</h2>' + ''.join(
            f'<div><code>{f.stem}</code> <audio controls preload="none" src="{f.name}"></audio></div>' for f in files))
    page = TAKES / 'index.html'
    page.write_text('<!doctype html><meta charset="utf-8"><title>Audience takes</title>'
                    '<style>body{font:15px system-ui;margin:2em} div{display:flex;gap:1em;align-items:center;margin:.3em 0} code{width:7em}</style>'
                    '<h1>Audience takes still to pick</h1>'
                    f'<p>Already picked (hidden here): {", ".join(sorted(approved)) or "none"}.</p>'
                    '<p>Played as generated; in the mix each sits far back and much quieter.</p>' + ''.join(rows))
    return page


def picks() -> dict[str, list[Path]]:
    """The kept takes of each kind."""
    kept = {}
    for f in sorted(KEPT.glob('*.mp3')):
        kept.setdefault(f.stem.rsplit('_', 1)[0], []).append(f)
    return kept


def keep(kind: str, letters: list[str]) -> list[Path]:
    """Copy takes of a kind into assets/audience/, lettered on from what's kept."""
    import shutil
    have = picks().get(kind, [])
    out = []
    for i, t in enumerate(letters):
        f = KEPT / f'{kind}_{"abcdefghijklmnopqrstuvwxyz"[len(have) + i]}.mp3'
        KEPT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TAKES / f'{kind}_{t}.mp3', f)
        out.append(f)
    return out


def conductor_take(line: str) -> Path | None:
    """The picked take of a conductor's line, if there is one: the default
    line's in assets/conductor/, any other line's (dedications name real
    people) only in the uncommitted engine/audience/conductor/picks.json."""
    from chorale import conductor
    shipped = CONDUCTOR / 'lines.json'
    if shipped.exists() and line in (lines := json.loads(shipped.read_text())):
        return CONDUCTOR / lines[line]
    local = conductor.LINES / 'picks.json'
    takes = json.loads(local.read_text()) if local.exists() else {}
    return conductor.LINES / f'{takes[line]}.mp3' if line in takes else None


SR = 24000
PRE = 5.0            # seconds of the hall before the first note: they're about to begin
ACTIVE = 2.6         # ...the stage getting into place for the first of them; then it quiets
# The choir knows when they'll start; the audience doesn't. The stage stops
# before the first note; the audience goes on until the baton goes up (a few
# watching hush a little), and only settles once they hear the singing
AT_BATON = 0.8       # the audience's noise once the baton is up
REACT_S = 0.6        # seconds before anyone reacts to the first note
# Loudness of each kind in the mix (LUFS), the music being at -20, at the
# default liveliness; everything far under the music
LEVEL = {'walk_on': -50, 'risers': -50, 'folders': -50, 'settle': -48, 'seats': -54,
         'cough': -47, 'rustle': -52, 'pew': -53, 'false_start': -40,
         'applause': -28, 'applause_hesitant': -28, 'applause_finale': -27,
         'baton': -60, 'score_page': -58, 'stand': -61}
CONDUCTOR_LUFS = -27   # his line, room and all: up by the choir, not on a microphone
UNSETTLED_DB = 3       # the hall while he talks: nobody quite listening yet
# The intro around his line: he starts a moment in, then a hush, a page, the baton, the first note
INTRO_IN, INTRO_HUSH, PAGE_AFTER, BATON_BEFORE = 1.2, 1.4, 0.5, 1.0
# Each sound is darkened a little and sent into the same church as the choir,
# so it sits back in the hall instead of on the microphones (the takes come
# back reverberant already; this puts them in this room)
DARKEN_HZ, ROOM_SEND_DB = 5000, -6
BED_HZ = 2500        # the stage noise before the music darker still: background, not events
BED_INTO = 10.0      # ...carrying on under the first seconds of the music as people settle
DURING = ('cough', 'cough', 'rustle', 'pew', 'seats')   # what may sound in a break between phrases (coughs most)
PRESENCE = ('rustle', 'pew', 'seats')          # the faint audience under the whole piece
LIVELY = 0.35        # the default: a well-behaved audience that is still there
# How liveliness (0 nobody .. 1 a badly behaved audience) sets things:
def every(l): return 40 - 32 * l             # seconds: one sound in a break at most this often
def chance(l): return min(1.0, 0.1 + 0.9 * l)        # that a break gets one
def presence_per_min(l): return 30 * l * l           # faint sounds under the music, per minute
def louder_db(l): return 10 * (l - LIVELY)            # every level, raised or lowered
INTO_MUSIC = 0.55    # liveliness from which a cough may land while they sing
# Restlessness over the piece (1 before the first note): people take a few
# seconds to settle once the singing starts, never quite all the way, and let
# go again when it stops: held coughs and shifting under the applause
SETTLE_S, SETTLED = 3.5, 0.25
def release_count(l): return 1 + 5 * l               # sounds let go of once the applause starts
LET_GO_S = 2.0       # seconds into the applause before people are fully at ease
TAIL_S = 0.5         # the track ends this long after the last clap: the applause's end is the end
RELEASE_GAP = 0.8    # seconds at least between the sounds they let go of: spread out, not all at once
BATON_CHANCE, PREP_CHANCE = 0.8, 0.5   # the conductor, speaking or not: baton up before the first note, and a page or the stand
ROOM_TONE, HISS = -60, -72   # LUFS of the church's air and the microphones' noise floor


def _load(f: Path) -> np.ndarray:
    y, _ = librosa.load(f, sr=SR, mono=False)
    return np.stack([y, y], 1) if y.ndim == 1 else y.T


def _at(x: np.ndarray, lufs: float) -> np.ndarray:
    m = pyloudnorm.Meter(SR, block_size=min(0.4, len(x) / SR * 0.9))
    now = m.integrated_loudness(x)
    return x * 10 ** ((lufs - now) / 20) if np.isfinite(now) else x


def room_air(n: int, seed: int = 8) -> np.ndarray:
    """The church's quiet air: brown noise between 40 Hz and 2.2 kHz,
    drifting slowly, a little different each side."""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    brown = np.cumsum(rng.standard_normal((n, 2)), 0)
    brown = sosfilt(butter(2, [40, 2200], 'bandpass', fs=SR, output='sos'), brown, axis=0)
    t = np.arange(n) / SR
    drift = np.stack([1 + 0.12 * np.sin(2 * np.pi * t / 11), 1 + 0.12 * np.sin(2 * np.pi * t / 13 + 1)], 1)
    return _at(brown * drift, ROOM_TONE)


def hiss(n: int, seed: int = 9) -> np.ndarray:
    return _at(np.random.default_rng(seed).standard_normal((n, 2)), HISS)


def sounding(x: np.ndarray, floor: float = 0.03) -> float:
    """Seconds until a take's sound actually stops (its last moment above floor of its peak)."""
    env = np.convolve(np.abs(x).mean(1), np.ones(SR // 20) / (SR // 20), 'same')
    loud = np.flatnonzero(env > floor * env.max())
    return (loud[-1] + 1) / SR if len(loud) else 0.0


def restlessness(t: float, baton_up: float, start: float, last_end: float, clap_at: float | None = None) -> float:
    """How restless the audience is at t (1 fully): fully before the baton, a
    little less once it's up, settling a moment after the first note, faint
    through the piece, still through the silence after the last chord, and
    letting go only once the applause has started."""
    clap_at = last_end if clap_at is None else clap_at
    if t < baton_up:
        return 1.0
    if t > last_end:
        return SETTLED if t < clap_at else min(1.0, SETTLED + (1 - SETTLED) * (t - clap_at) / LET_GO_S)
    if t < start + REACT_S:
        return AT_BATON
    return SETTLED + (AT_BATON - SETTLED) * np.exp(-(t - start - REACT_S) / SETTLE_S)


def place(out: np.ndarray, sound: np.ndarray, at: float, pan: float) -> None:
    i = int(at * SR)
    j = min(len(out), i + len(sound))
    if j <= i:
        return
    angle = (pan + 1) * np.pi / 4
    mono = sound[:j - i].mean(1)
    out[i:j, 0] += mono * np.cos(angle) * np.sqrt(2)
    out[i:j, 1] += mono * np.sin(angle) * np.sqrt(2)


def darken(x: np.ndarray) -> np.ndarray:
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, DARKEN_HZ, 'lowpass', fs=SR, output='sos'), x, axis=0)


def into_room(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    from scipy.signal import fftconvolve
    x = darken(x)
    wet = np.stack([fftconvolve(x[:, c], ir[:, c]) for c in range(2)], 1)   # the whole tail: cut short, it stops dead
    wet *= 10 ** (ROOM_SEND_DB / 20) * np.sqrt(np.mean(x ** 2)) / max(np.sqrt(np.mean(wet ** 2)), 1e-12)
    out = np.zeros_like(wet); out[:len(x)] += x
    return out + wet


def conductor_line(take: Path, ir: np.ndarray, seed: int) -> np.ndarray:
    """His line staged (conductor.py) and set back by the choir in the church."""
    from chorale import conductor, room
    dry = conductor.staged(conductor.spoken(take), seed)
    _, send_db = room.place(np.zeros(1), room.Seat(*conductor.STAND))
    send = dry * 10 ** (send_db / 20)
    from scipy.signal import fftconvolve
    wet = np.stack([fftconvolve(send[:, c], ir[:, c]) for c in range(2)], 1)
    wet *= 10 ** (room.ROOMS['church'].wet_db / 20) * np.sqrt(np.mean(dry ** 2)) / max(np.sqrt(np.mean(wet ** 2)), 1e-12) * 1.5
    out = wet.copy(); out[:len(dry)] += dry
    return _at(out, CONDUCTOR_LUFS)


def live(music: np.ndarray, phrases: list[list[float]], offset: float, chosen: dict[str, list[Path]], seed: int = 0,
         liveliness: float = LIVELY, applause_kind: str = 'applause', room_name: str = 'church',
         intro: Path | None = None, events: list | None = None, crowd: float = 1.0) -> np.ndarray:
    """The church mix (music at -20 LUFS, its score's 0 at offset seconds) heard
    live at a liveliness from 0 (nobody: the room's air alone) to 1 (a badly
    behaved audience): the stage settling as they're about to begin, carrying
    on under the first bars; the audience faintly there under the piece; now
    and then a small sound in a break between phrases (and at high liveliness
    a cough while they sing); applause as the last chord dies away. With an
    intro (a conductor take), he speaks first over a hall not yet listening,
    then a hush, a page turned, the baton picked up, and the first note.
    Without one he's still there: the baton (most of the time) before the
    first note. crowd scales how many people there are (1 the size the levels
    were set at): more small sounds, a slightly louder hall, fuller applause.
    events, if given, collects (seconds, kind) of each sound placed."""
    from scipy.signal import butter, sosfilt
    from chorale import room
    ir = room.impulse(room.ROOMS[room_name])
    rng = np.random.default_rng(seed)
    l = float(np.clip(liveliness, 0, 1))
    up = louder_db(l) + 5 * np.log10(crowd)   # more people: a little louder (half of what their count alone would give)

    def pick(kind, db=0.0):
        if not chosen.get(kind):
            return None
        x = _load(chosen[kind][rng.integers(len(chosen[kind]))])
        # applause takes carry their own hall: put through this one too, the claps smear
        x = darken(x) if kind.startswith(('applause', 'false_start')) else into_room(x, ir)
        return _at(x, LEVEL[kind] + db)

    def log(at, kind):
        if events is not None:
            events.append((round(float(at), 2), kind))

    def end_fade(x, secs):
        k = min(len(x), int(secs * SR)); x[-k:] *= np.linspace(1, 0, k)[:, None]; return x

    speech = conductor_line(intro, ir, seed) if intro is not None else None
    pre = PRE if speech is None else INTRO_IN + len(speech) / SR + INTRO_HUSH + PAGE_AFTER + BATON_BEFORE + 0.6
    start = pre + offset + (phrases[0][0] if phrases else 0.0)        # the first note
    last_end = pre + offset + (phrases[-1][1] if phrases else len(music) / SR)
    applause = pick(applause_kind) if l > 0 else None
    clap_at = last_end + 1.0                      # while the last chord is dying away
    clap_end = clap_at + (sounding(applause) if applause is not None else 0.0)
    n = max(int(pre * SR) + len(music), int((clap_end + TAIL_S) * SR))
    out = np.zeros((n, 2))
    out[int(pre * SR):int(pre * SR) + len(music)] += music
    if l > 0:
        # Before: one soft background of the stage settling, darker, no single sound
        # standing out, carrying on under the first bars and fading away
        baton_up = start - BATON_BEFORE

        restless = lambda t: restlessness(t, baton_up, start, last_end, clap_at)

        # The stage: the choir getting into place, done before they sing
        busy = start - (pre - ACTIVE)
        stage = np.zeros((int(start * SR), 2))
        for kind, at in (('risers', 0.0), ('folders', 0.4)):
            x = pick(kind, up)
            if x is not None:
                x = end_fade(x[:max(1, int((busy - at) * SR))], 0.5)
                stage[int(at * SR):int(at * SR) + len(x)] += x
        # The audience: settling, and shifting about, as restless as they are at each moment
        hall = np.zeros((int((start + BED_INTO) * SR), 2))
        x = pick('settle', up)
        if x is not None:
            hall[:min(len(hall), len(x))] += x[:len(hall)]
        for _ in range(int(2 + 3 * l)):
            x = pick(('seats', 'rustle')[rng.integers(2)], up)
            if x is not None:
                at = rng.uniform(0, start)
                x = end_fade(x[:max(1, len(hall) - int(at * SR))], 0.2)
                hall[int(at * SR):int(at * SR) + len(x)] += x
        if speech is not None:
            # nobody quite listening while he talks: the hall's own shifting goes on under him
            for _ in range(int(2 + 4 * l)):
                x = pick(('seats', 'rustle', 'settle')[rng.integers(3)], up + UNSETTLED_DB)
                if x is not None:
                    at = rng.uniform(0, INTRO_IN + len(speech) / SR)
                    x = end_fade(x[:max(1, len(hall) - int(at * SR))], 0.2)
                    hall[int(at * SR):int(at * SR) + len(x)] += x
        hall[:len(stage)] += stage
        hall = sosfilt(butter(2, BED_HZ, 'lowpass', fs=SR, output='sos'), hall, axis=0)
        k = int(0.3 * SR); hall[:k] *= np.linspace(0, 1, k)[:, None]
        envelope = np.array([restless(t) for t in np.arange(0, len(hall), SR // 100) / SR])
        hall *= np.interp(np.arange(len(hall)), np.arange(len(envelope)) * (SR // 100), envelope)[:, None]
        out[:len(hall)] += hall
        # Under the piece: the audience there, busier while they settle, then faint
        span = last_end - start
        for _ in range(rng.poisson(crowd * presence_per_min(l) / SETTLED * span / 60)):
            at = rng.uniform(start, last_end)
            r = restless(at)
            if rng.random() > r:
                continue   # thinned: most of these fall while people are still settling
            kind = PRESENCE[rng.integers(len(PRESENCE))]
            x = pick(kind, up - 6 + 6 * (r - SETTLED) / (AT_BATON - SETTLED))
            if x is not None:
                place(out, end_fade(x, 0.2), at, rng.uniform(-0.9, 0.9))
                log(at, f'{kind} ({"settling" if r > 0.5 else "faint"}, under the music)')
        # In the breaks: now and then a small sound as a phrase's last chord
        # releases. A chorale's breaks are only a breath long, so it starts in
        # the breath and plays out under the next phrase's start, as concert
        # coughs do
        quiet_until = 0.0
        for (_, b), _next in zip(phrases, phrases[1:]):
            at = pre + offset + b + 0.05
            if at < quiet_until or rng.random() > chance(l):
                continue
            kind = DURING[rng.integers(len(DURING))]
            x = pick(kind, up)
            if x is not None:
                place(out, end_fade(x, 0.15), at, rng.uniform(-0.8, 0.8)); log(at, f'{kind} (as a phrase ends)')
                quiet_until = at + every(l)
        # A badly behaved audience coughs while they sing, too
        if l >= INTO_MUSIC:
            for _ in range(rng.poisson((l - INTO_MUSIC) * 20 * span / 60)):
                x = pick('cough', up)
                if x is not None:
                    at = rng.uniform(start, last_end)
                    place(out, x, at, rng.uniform(-0.9, 0.9)); log(at, 'cough (while they sing)')
        # Once the applause starts, what people held in: let go through it and
        # after, spread out at a natural pace (never in the silence before it)
        span_end = clap_end - 1.0   # everything let go of lands inside the applause, none after it
        times, t = [], clap_at + 0.5
        want = rng.poisson(crowd * release_count(l))
        while len(times) < want and t < span_end:
            t += RELEASE_GAP + rng.exponential((span_end - clap_at) / max(want, 1))
            if t < span_end:
                times.append(t)
        for at in times:
            kind = ('cough', 'cough', 'seats', 'rustle')[rng.integers(4)]
            x = pick(kind, up + 2)
            if x is not None:
                place(out, end_fade(x, 0.15), at, rng.uniform(-0.9, 0.9)); log(at, f'{kind} (let go as it ends)')
    if speech is not None:
        i = int(INTRO_IN * SR); out[i:i + len(speech)] += speech[:len(out) - i]
        log(INTRO_IN, 'conductor speaks')
        after = INTRO_IN + len(speech) / SR
        prep = [('stand', after + 0.4), ('score_page', after + INTRO_HUSH), ('baton', start - BATON_BEFORE)]
    else:
        prep = ([(('score_page', 'stand')[rng.integers(2)], max(0.3, start - BATON_BEFORE - 1.2))] if rng.random() < PREP_CHANCE else []) \
             + ([('baton', start - BATON_BEFORE)] if rng.random() < BATON_CHANCE else [])
    if l > 0 or speech is not None:
        for kind, at in prep:
            x = pick(kind, up)
            if x is not None:
                place(out, x, at, 0.05); log(at, kind)
    if applause is not None:
        place(out, applause, clap_at, 0.0); log(clap_at, applause_kind)
        if crowd > 1.15 and len(chosen.get(applause_kind, [])) > 1:
            # more hands: a second take under the first, a moment behind it
            more = pick(applause_kind, 10 * np.log10(crowd - 1))
            if more is not None:
                place(out, more, clap_at + 0.25, 0.0); log(clap_at + 0.25, f'{applause_kind} (more hands)')
    out += room_air(n) + hiss(n)
    peak = np.abs(out).max()
    return out * min(1.0, 10 ** (-1 / 20) / peak)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    opt = dict(a[2:].split('=', 1) for a in sys.argv[2:] if a.startswith('--') and '=' in a)
    if cmd == 'generate':
        print(generate(opt.get('more')))
    elif cmd == 'picks':
        print(json.dumps({k: [p.name for p in v] for k, v in picks().items()}, indent=1))
    elif cmd == 'keep':
        for f in keep(sys.argv[2], sys.argv[3:]):
            print(f)
    else:
        raise SystemExit(__doc__)
