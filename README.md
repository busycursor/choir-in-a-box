# choir-in-a-box

Put in a webpage or a score and get back a choir singing it, either in four parts or a full mixed choir. Supports multiple room and church types and can add in an audience. Multilingual, professional, and realistic. Runs entirely locally.

## Listen

### Choir alone

| | |
|---|---|
| [BWV 14.5, *Wär Gott nicht mit uns diese Zeit*](https://busycursor.github.io/choir-in-a-box/examples/01-bwv14.5-full-choir-large-church-live.mp3) | full choir, large church, a live audience |
| [BWV 227.7, *Jesu, meine Freude*](https://busycursor.github.io/choir-in-a-box/examples/02-bwv227.7-full-choir-church-live.mp3) | full choir, a smaller church |
| [BWV 5.7, *Wo soll ich fliehen hin?*](https://busycursor.github.io/choir-in-a-box/examples/03-bwv5.7-quartet-small-church-live.mp3) | quartet, a small church, a restless audience |
| [Mozart, *Leck mich im Arsch*, K. 231](https://busycursor.github.io/choir-in-a-box/examples/04-mozart-k231-six-part-choir-church-live.mp3) | a famous six-part canon |

### With accompaniment

The accompaniment is generated from the score. Where a score has a continuo part with figured bass, the figures are realized by the rules Bach's contemporaries taught (no parallel fifths or octaves, the right hand under the melody, the right notes doubled); a chorale has no figures, so its continuo is realized from the choir's own harmony, chord by chord. Then each instrument plays it in its own way: the organist changes registration with the form, the harpsichordist rolls and ornaments, the pianist shapes the phrases.

| | |
|---|---|
| [BWV 14.5, *Wär Gott nicht mit uns diese Zeit*](https://busycursor.github.io/choir-in-a-box/examples/05-bwv14.5-full-choir-large-church-organ-live.mp3) | full choir with organ continuo, large church, a live audience |
| [BWV 227.7, *Jesu, meine Freude*](https://busycursor.github.io/choir-in-a-box/examples/06-bwv227.7-full-choir-church-piano-live.mp3) | full choir with piano, a smaller church |
| [BWV 5.7, *Wo soll ich fliehen hin?*](https://busycursor.github.io/choir-in-a-box/examples/07-bwv5.7-quartet-small-church-harpsichord-live.mp3) | quartet with harpsichord continuo, a small church, a restless audience |

## What it does

- **Reads any score.** A MusicXML file (`.musicxml`, `.xml`, `.mxl`), a link to one, or any web page with MusicXML on it: it finds the scores on the page or in scripts, and a `#name` on the link chooses one.
- **Sings it with real voices.** The singers are the 20 professional singers of [VocalSet](https://zenodo.org/records/1442513) (sopranos, mezzos, a countertenor, tenors, baritones, basses), sung through [SoulX-Singer](https://github.com/Soul-AILab/SoulX-Singer). Parts are mapped to range or moved through octaves to build the correct mix.
- **Performance variation.** Slowing into fermatas, longer ending. Phrases swell and ease into cadence, and singers take breaths at different moments.
- **Venue variation.** Singers are placed spatially in a choir formation: sopranos to basses left to right, men a row behind, a section spread across its place.
- **Optionally, with an accompaniment.** An organ, a harpsichord or a piano plays with the choir, read from the score: a continuo part where there is one (figured bass realized by the period rules), or the chorale's own harmony. The organ is synthesized, with stops, couplers, a swell box and registrations that change with the music's form; the harpsichord and piano are sampled, played with arpeggiation, ornaments and phrasing. A skill setting makes the player anything from a virtuoso to someone who loses their place. Each stands in the room with the choir: the organ in the gallery, the others by the basses.
- **Optionally, in front of an audience.** The stage settling, a conductor's baton, people shifting and the odd cough between phrases, applause at the end, set by how lively they are. Some people may accidentally clap between movements. The conductor (cloud-only) can introduce the piece first.

## Install

Built and tested on an Apple Silicon Mac with GPU. Needs testing on NVIDIA GPU; should work or be easily adaptable. Needs [uv](https://docs.astral.sh/uv/) and, on a Mac, [Homebrew](https://brew.sh):

```bash
git clone https://github.com/busycursor/choir-in-a-box.git
cd choir-in-a-box
scripts/install.sh
```

It installs espeak-ng and ffmpeg, SoulX-Singer (its code, a Python environment and its 2.6 GB model, plus the Whisper model it uses) the VocalSet singers (about 220 MB of their recordings) and the sampled harpsichord and piano (about 850 MB), all into `engine/`, then runs the tests. About 5 GB in all.

## Use

```bash
P=engine/soulx/.venv/bin/python

$P -m chorale path/to/score.musicxml                          # full choir, large church
$P -m chorale https://example.org/page-with-scores#piece-name --audience
$P -m chorale score.musicxml --choir=quartet --venue=small_church --audience=0.9
$P -m chorale score.musicxml --audience --conductor          # he introduces it first
$P -m chorale https://example.org/page-with-scores --all     # every score on the page
$P -m chorale score.musicxml --accompaniment=organ           # with an organ (or harpsichord, piano)
```

Output goes to `engine/renders/<name>/`. No optimization at this time, on M4 Pro render speed is about 0.3x realtime, per singer, so rendering as many as 18 can take awhile. For remixing existing parts, `--mix-only` re-mixes a finished render without regeneration.

| Option | |
|---|---|
| `--choir=full\|quartet` | the full mixed choir (default) or one singer per part; `choirs/*.json` are the castings |
| `--venue=small_church\|church\|large_church\|larger_church` | the room and the size of the crowd |
| `--audience[=0.35]` | a live audience, from 0 (nobody) to 1 (badly behaved) |
| `--applause=applause\|applause_hesitant\|applause_finale` | polite, hesitant, or cheering |
| `--conductor[="his line"]` | the conductor speaks first (ElevenLabs only) |
| `--literal` | sing exactly what's written, no interpretation |
| `--bpm=N`, `--lang=de\|en` | tempo (else the score's, or default 72) and language (else told from the lyrics) |
| `--stop=<bar>.<beat>` | everyone ends together there, held: for a canon that would go round forever |
| `--seed=N` | a different audience on the same performance |
| `--accompaniment=organ\|harpsichord\|piano` | an instrument plays with the choir, from the score |
| `--accompaniment-style=continuo\|doubling` | realize the continuo (organ and harpsichord's default) or play the voices' parts (piano's default) |
| `--registration=continuo\|continuo_bright\|chorale\|soft\|plenum\|reed` | organ: one registration throughout, instead of changing with the form |
| `--skill=0.6` | the accompanist: 0.6 a competent player; toward 1 more ornaments and flourishes, well played; below about 0.45 wrong notes and fumbles; near 0 a breakdown, a stop and a search for the place |
| `--dry-run` | part mapping only |

## How it works

Score → parts (`score_parts.py`: repeats, lyrics laid on every part, pronunciation, the tempo map) → singing (`sing_parts.py`, `soulx_render.py`: each phrase sung by SoulX-Singer in each singer's voice, checked for wrong notes and sung again if one slips) → an accompaniment if asked (`accompany.py`, `realize.py`, `organ.py`, `sampler.py`) → the room (`room.py`) → the audience (`audience.py`) → MP3 (`finish.py`). [docs/how-it-works.md](docs/how-it-works.md) has the detail [AI-generated documentation], and the reasons behind the less obvious parts.

## Credits

- Singing: [SoulX-Singer](https://github.com/Soul-AILab/SoulX-Singer) (Apache 2.0)
- Voices: [VocalSet](https://zenodo.org/records/1442513), Wilkins, Seetharaman, Wahl and Pardo, ISMIR 2018, and its note annotations, [Annotated-VocalSet](https://zenodo.org/records/7061507), Faghih and Timoney, *Applied Sciences* 2022. (All CC BY 4.0)
- Harpsichord and piano: the [Versilian Community Sample Library](https://github.com/sgossner/VCSL) (CC0), downloaded by the installer.
- SFX and conductor are ElevenLabs.

## Find this

An open-source AI choir: singing voice synthesis that turns sheet music (MusicXML) into a realistic choir recording, from a four-part quartet to a full SATB choir, with a church acoustic and an optional live audience. With organ, harpsichord or piano accompaniment realized from the score. For Bach chorales, hymns, canons and part-songs; for hearing a choral score before rehearsal, or a demo recording of one. A summary for language models and AI assistants is in [llms.txt](https://busycursor.github.io/choir-in-a-box/llms.txt).

## License

MIT, (c) 2026 BusyCursor: free to use and modify, keeping the copyright notice. SoulX-Singer and VocalSet keep their own licenses (above).
