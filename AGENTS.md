# Working on choir-in-a-box

## Documentation goes with every feature

A feature isn't done until it's documented, in the same change:

- **README.md**: what it does and how to use it (the option, an example command).
- **llms.txt**: the same, briefly, so assistants that read it know the feature exists.
- **docs/how-it-works.md**: how it works and why, especially anything learned by ear.

## Conventions

- **Tests run offline**: `engine/soulx/.venv/bin/python -m pytest tests`. Nothing in them runs SoulX or downloads anything; use fixtures and synthetic audio.
- **Anything downloadable is fetched by `scripts/install.sh`** into `engine/` (gitignored), never committed: models, datasets, instrument samples. What's committed is code, the voice and choir definitions, and the small audio picked by ear (`assets/`).
- **Seeded randomness**: anything random (audience, breathing, an organist's timing, a realization's choices) takes a seed, so a render can be reproduced. Seed from stable values, never `hash()` of a string, which changes between runs.
- **Judged by ear**: measurements find problems, but whether something sounds right is a listening decision. Keep the reason for a non-obvious value next to it in the code.
- **No personal names, paths or accounts** in anything committed: the repo is public.
