## The chain

```
score ─► scores.py ─► score_parts.py ─► parts.json ─► sing_parts.py ─► soulx_render.py ─► a track per singer
                                                                                              │
              MP3 ◄─ finish.py ◄─ audience.py (optional) ◄─ room.py ◄─────────────────────────┘
```

`python -m chorale` (`chorale/__main__.py`) runs all of it. `engine/` is loaded by the install script: SoulX-Singer and its environment, the VocalSet recordings, the voice prompts, the renders.

## 1. Finding the score (`scores.py`)

A file, a link, or a page. A page is searched for anything ending in a score extension (`.musicxml`, `.xml`, `.mxl`, or `.json`, which some pages use to carry MusicXML with other data), in the page and in its own scripts, including a template path like `` `data/${id}.json` `` filled in from the link's `#fragment`. Each candidate is downloaded and kept if found to be a store. Downloads are cached in `engine/scores/`, and a cached score can be named by its file name or the end of it.

## 2. The parts (`score_parts.py`, `timing.py`)

- **Repeats** are taken (a data file's own playback timeline if it has one, else music21's expansion). `--stop=<bar>.<beat>` cuts every part at one beat, counted as performed, and holds that chord, allowing endless repetition to end after a fashion.
- **Lyrics** are laid on every part by timing from the part with the words.
- **Pronunciation:** English through CMUdict (g2p_en for the rest); German through espeak-ng's IPA; Italian and church Latin (the VocalSet excerpts) through espeak-ng's Italian to replicate Latin speech. `<score>.say` contains pronunciation overrides.
- **The tempo map** is how the piece is performed, shared by every part to move together (like a conductor). A score with fermatas is read as a chorale is sung: a slight slowing over the beat into each fermata, the fermata held half as long again, a broader slowing over the last bar, and the last chord held three times its written length. (disable with `--literal`)
- **Phrases** run fermata to fermata and drive the dynamics.

## 3. Singing (`sing_parts.py`, `soulx_render.py`, `pitchcheck.py`)

SoulX-Singer sings notes and phonemes in the voice of a short sung prompt. It knows English, Mandarin and Cantonese phonemes only, so German is spelled in the nearest English ones (`sing_parts.arpabet`).

Notes

- **Sing phrase by phrase, each pinned to its time.** SoulX doesn't adhere in long silences, so parts are split by rests and breath to be placed appropriately.
- **Syllables, not words.** Given a whole word over a melisma, SoulX keeps singing its first syllable. Each syllable gets its own phonemes, pinned to starting note.
- **Consonants before the beat.** A syllable's opening consonants start a little early, taken from the note before, to land the vowel on beat.
- **A run-up before every phrase, dropped afterwards.** SoulX sings a phrase as a continuation of the voice prompt, and at that hand-over it sometimes jumps the gun: a burst, a click, or the phrase's first sound (a stray "v" before "Wär'"), whatever the seed. Each phrase gets 0.4 s of silence first.
- **Wrong notes are caught and sung again.** Now and then SoulX puts a note an octave off, or opens a note on the next note's pitch. The renderer measures every note against the score and sings the phrase again with the next seed, up to three times. A slip counts only when two pitch trackers agree (harvest and pyin).
- **Seeded,** ensures consistent rendering.
- **A section** is several singers on one part, each with their own prompt and each phrase moved by up to ±20 ms to avoid eerie unison.

## 4. The voices (`voices.py`, `import_vocalset.py`, `choir.py`)

The voices are VocalSet's 20 professional singers, each singing three excerpts in straight tone and with vibrato; Annotated-VocalSet gives every note's timing, pitch and syllable, so each excerpt becomes a prompt directly. The prompts in use are each singer's straight-tone *Dona nobis pacem*: straight tone blends, and its vowels are pure. Each singer's range is the usual range of the voice type VocalSet gives them.

Casting (`choirs/*.json`): each part's singers. Lines are fit to singers in range, and if no singers are in range an octave move is prescribed.

## 5. The room (`room.py`)

- **Balance first:** SoulX sings each voice at its own level, so every part is brought to the same loudness, a section as a whole, then set: the tune on top, the bass just under, the inner voices a little under that. (This would need tweaking for other types of music.)
- **Phrasing:** every phrase in a little under the level, swelling toward its middle, easing into its cadence; the last phrase is softer.
- **Staggered breathing:** singers have breath for about 5-8s. If this runs out they take a short breath inside a long note, never more than a third of the section at once. Soloists can breathe only at the rests.
- **Seats spatial orientation:** sopranos to basses left to right, the men a row behind, a section spread across its place in two ragged rows; other parts evenly across the front.
- **Venues** pair a synthesized room (decorrelated pink noise per side, exponential tail, early reflections, pre-delay, calibrated so its level means the same in every room) with a crowd size.

## 6. The accompaniment (`accompany.py`, `realize.py`, `organ.py`, `sampler.py`)

`--accompaniment=organ|harpsichord|piano`, mixed in `finish()` (so `--mix-only` can add it to any render).

- **Timing.** `score_parts.py` records every part's notes in score beats as performed (`events` in `parts.json`); the accompaniment places them through the same tempo map the choir sang to, plus the render's lead-in, so it holds and moves with the singers, exactly on the beat before any human looseness is added. Renders from before `events` existed get their parts rebuilt from the score and checked against what was sung.
- **The harmony.** A score that encodes figured bass (MusicXML `<figured-bass>`) is read figure by figure. A chorale encodes none: there the figures are the choir, so each chord is read from the voices at every bass note and at each beat where the harmony over a held bass changes (a 4-3 resolving), not at offbeat passing notes.
- **The realization.** Every right-hand voicing of each chord (three voices, four in the organ's fullest section) is a candidate; a best-path search over the piece picks the sequence that moves least, never makes parallel fifths or octaves (with the bass or within the hand), stays under the melody, keeps voices within an octave, and doubles by the rules (never the leading note or a seventh). Seeded tie-breaks: a different seed is a different correct realization.
- **The organist.** The pedal plays the bass, the right hand holds chords with common tones tied, a small lift before each phrase. Registration follows the form: a phrase whose tune repeats an earlier one starts the repeat, and what follows is the last section; a seeded plan picks e.g. bright flutes, then the soft continuo for the repeat, then principals with a four-voice right hand. Chords land 10–30 ms off the beat, mostly behind, notes not quite together, repeated bass notes detached: a player listening, not a sequencer.
- **The organ** is synthesized: each stop's family spectrum (principal, open and stopped flute, string, trumpet, oboe), its speech (attack, chiff), wind noise, seeded per-pipe detuning (`zlib.crc32`, never `hash()`, which changes between runs); mixtures that break back; a celeste tuned sharp; couplers, octave couplers, a swell box (quieter and darker as it shuts) and a tremulant. Pipes stand in a case: pedal towers wide, Great centre, Swell behind; C side and C-sharp side fanning out from middle C; each pipe a fraction of a millisecond later at the far ear, so it sounds placed rather than panned.
- **The harpsichordist** (seeded, chord by chord): rolled chords (broader at cadences, bass doubled below), long chords broken across the beat in eighths or re-struck, passing notes filling thirds in the top voice, the odd acciaccatura, a trill from the upper note into each cadence.
- **The pianist** plays the four parts: each phrase swells and eases, the tune louder and a few ms ahead, cadences rolled, the pedal held through each harmony, the last bass doubled an octave down. Three recorded dynamic layers (soft, middle, loud) are picked by touch, with the natural level step between them put back (the library normalized them).
- **Samples** (`fetch_instruments.py`): VCSL's Flemish harpsichord and Steinway B, CC0. Their pitch is measured, not read from file names (the harpsichord's are named an octave below what they sound); the median offset over each instrument's samples is used, since a deep bass note's weak fundamental can measure an octave off.
- **Skill** (`skill.py`, `--accompaniment-skill`, or `--skill` for choir and accompanist both; default 1.0, a fine player; 0.6 is a competent one). At 0.6 and above the timing is the style passes' human looseness, never tighter; below it gets looser, with a wandering rush or drag. The style passes ask `skill.chance()` for each ornament, so a better player ornaments more: trills, mordents on long top notes, broken chords, passing notes, acciaccaturas, and above 0.8 a run sweeping into each cadence (the organ adds mordents into cadences, the piano grace notes). Below 0.45 come mistakes: a wrong neighbouring key, usually corrected a beat of a second later, sometimes left; a key brushed with the right one; trills that stumble, and below 0.3 none attempted. Below 0.2, growing toward 0, fumbling throughout instead of occasional mistakes (by ear, a mostly-fine player with one disaster sounded wrong): late into chords, sometimes very late, finding a chord's notes one at a time, timid and uneven, falling behind the choir and skipping a chord to catch up, notes dropped and whole chords missed, most notes wrong and slowly corrected. Below 0.15, on top of that, a breakdown: part of a phrase on the wrong chords, an abrupt stop, a few quiet notes looking for the place, back in at the next phrase (twice below 0.07). With a choir, its breakdowns and when it gives up come from the plan it shares with the choir (section 7). All seeded.
- **In the room**: the organ in the gallery (far back, 6 dB under the choir, 5 dB more into the room: a big instrument fills a church; at 6 dB under, its full registrations stand out from the quiet ones), the harpsichord and piano by the basses. Instruments get neither the singers' breathing nor their phrase swell.

## 7. Choir skill (`choir_skill.py`, `ensemble.py`)

`--choir-skill` (or `--skill` for choir and accompanist both): 1, the default, a fine choir; 0.6 a competent one; the same curve as the accompanist's. Each singer errs on their own, seeded per singer, so a section covers its members' slips the way a real one does.

- **Everything is sung.** No fault is put on the finished audio: bending a voice's pitch afterwards rubber-bands it faster than anyone can sing. Faults change what each singer is asked to sing, and SoulX sings them. Below 0.6 each singer is sung twice: a first take (`<part>-take.wav`), whose own pitch curve (harvest, 20 ms frames, a frame far off its note put back on it) gets the faults drawn in, then sung again in SoulX's melody mode (`control="melody"`, an f0 contour instead of score notes; `<part>-sung.json`). That's twice the singing below 0.6, and a choir's faults are set when it's sung: `--mix-only` can't change them.
- **Pitchiness** (below 0.6): a slow wander around the note, scoops up into notes, vibrato calmed in the middle of some notes, and the choir sagging flat phrase by phrase (up to 45 cents by the end at 0). No drawn fault moves the pitch faster than 1800 cents a second, a quick but human glide.
- **Wrong notes in the obvious places** (below 0.45, in the score SoulX is given): a leap overshot or fallen short of, an accidental sung as the plain scale note, the top of a phrase a semitone short. Some are heard and slid onto the right note partway through.
- **Unsure notes** (below 0.45): a note started off its pitch and hunted for, swinging slowly round it (about a third never found), or missed by 2-5 semitones.
- **Mispronunciation** (below 0.45): vowels slid into their neighbours, final consonants swallowed, consonants softened or swapped (in the ARPAbet SoulX is given).
- **Entries** (below 0.45): a cue missed, the phrase taken up from a later note or sat out altogether, or jumped, the phrase a little early. Below 0.2 a singer loses the place for a phrase, a beat or two behind, its end dropped to catch up at the next. A phrase's notes start a little before its cue for their consonants; an entrance counts them as on it.
- **Collapse** (below 0.15): partway into a phrase every part gives up after the note it's on, until one part bravely finds the next entrance and the others join, a beat or two apart, one by one (twice below 0.07). Below 0.02 (skill 0, near enough) it falls apart for good, 40-60% of the way through (sooner, and the joke is over too fast): a try or two at a later entrance, sung from the phrase as written, comes to nothing, and the piece ends there.
- **With an accompanist** (`ensemble.py`), one plan made before the singing (`plan.json`, since the choir sings its part of it) says who falls apart where and how the other takes it. Every time in it is a place in the score as the tempo map has it, so whoever is playing or singing is always where the piece is meant to be. A choir collapse: an accompanist at 0.45 or better plays straight on and the choir finds it at the next entrance; a weaker one rallies for a few beats (playing harder), stops, and comes back at the entrance or a bar or so before it to get them going. The choir falling apart for good: once everyone stops singing the accompanist stops too, after a beat or two of rallying (five or six at best); a poor one may lose its place first, a beat or two on the wrong chords, and take them down with it; a good one may try once more, leading in to a later entrance, which the choir's last tries answer. Both below 0.07: nobody finds the first entrance after a collapse. An accompanist breakdown: a weak choir falls with it (the weaker, the likelier) and comes back when it does; a choir at 0.45 or better sings on. An accompaniment chosen later with `--mix-only` reacts to the collapses the choir already sang.
- **What happened** is printed as it's sung and mixed (`choir:` and `together:` lines) and kept in `choir.log`.

## 8. The audience (`audience.py`, `conductor.py`, `assets/`)

- **Levels:** everything far under the music, darkened, and sent through the same room as the choir, so it sits back in the hall.
- **Nobody is psychic.** Roll-up is timed based on the choir being aware when it will start; the audience is only aware the choir has started after they have time to react.
- **During:** faint shifting throughout; now and then a cough or rustle as a phrase releases (a chorale's breaks are a breath long, so it starts there and plays out); above 0.55 liveliness, coughs can occur while they sing.
- **The end:** stillness through the silence after the last chord; people let go only once the applause starts, spread through it, and the track ends with the last clap.
- **The applause follows how it went** (`audience.reaction()`): the choir's skill, pulled down partway by the accompanist's. From 0.6 the applause asked for; 0.3–0.6 polite and shorter (15 s down to 5 s), a little quieter; 0.1–0.3 a few people clapping out of time with each other; below that, or a piece that fell apart, a pause while nobody's sure it's over, then a few bewildered claps trailing off, or one person clapping alone. Below 0.2, a quarter of the time, someone shouts "Bravo!" into it anyway (spoken by an ElevenLabs stock voice: the sound-effects model gave a crowd shouting in Spanish). Never boos. When a piece falls apart for good, the audience hears its end where the sound stops, not where the score does.
- **Liveliness** (0–1) sets how often, how loud, and whether anything lands during the singing; **crowd** (from the venue) sets how many people.
- **The conductor** (`conductor.py`) speaks with the ElevenLabs voice "Conductor" (eleven_v4, stability 0.45), cued "[announcing to the assembled crowd with very slight reluctance]" unless a line has its own cue. To sound off the cuff rather than read: one small stutter written into the text ("dedicated to-to my"), capitals for stress ("Good EVENING."). Spatially oriented by the choir with no microphone of his own, and wanders and turns away and back as he talks (more for a longer speech). Use the conductor description if you want to recreate the voice or make your own.
