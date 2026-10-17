#!/usr/bin/env bash
# Sets choir-in-a-box up from a fresh clone: system tools, SoulX-Singer (code,
# Python environment and model), and the VocalSet voices. Everything lands in
# engine/, which git ignores. Run from the repository's root: scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
SOULX_REV=81aeb3ae772c70093c3de74dc23c92d983801ae4   # the SoulX-Singer revision this was built on

echo "== system tools (espeak-ng for pronunciation, ffmpeg for audio)"
if [[ "$(uname)" == Darwin ]]; then
  command -v brew >/dev/null || { echo "needs Homebrew: https://brew.sh"; exit 1; }
  for t in espeak-ng ffmpeg; do command -v "$t" >/dev/null || brew install "$t"; done
else
  for t in espeak-ng ffmpeg; do command -v "$t" >/dev/null || sudo apt-get install -y "$t"; done
fi
command -v uv >/dev/null || { echo "needs uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }

echo "== SoulX-Singer at $SOULX_REV"
mkdir -p engine
if [[ ! -e engine/soulx ]]; then
  git clone --quiet https://github.com/Soul-AILab/SoulX-Singer.git engine/soulx
  git -C engine/soulx checkout --quiet "$SOULX_REV"
fi
if [[ ! -x engine/soulx/.venv/bin/python ]]; then
  uv venv --quiet --python 3.10 engine/soulx/.venv
fi
uv pip install --quiet --python engine/soulx/.venv/bin/python -r requirements.txt
P=engine/soulx/.venv/bin/python
$P - <<'PY'
from huggingface_hub import hf_hub_download
for f in ('model.pt', 'config.yaml'):
    hf_hub_download('Soul-AILab/SoulX-Singer', f, local_dir='engine/soulx/pretrained_models/SoulX-Singer')
from transformers import WhisperFeatureExtractor, WhisperModel   # SoulX fetches it on first use otherwise
WhisperFeatureExtractor.from_pretrained('openai/whisper-base'); WhisperModel.from_pretrained('openai/whisper-base')
import nltk
nltk.download('cmudict', quiet=True)
PY

echo "== VocalSet: 20 professional singers' sung excerpts and their notes"
$P -m chorale.fetch_vocalset
$P -W ignore -m chorale.import_vocalset > /dev/null
echo "   $(ls voices | wc -l | tr -d ' ') voices"

echo "== instruments: a Flemish harpsichord and a Steinway grand from VCSL (the organ is synthesized)"
$P -W ignore -m chorale.fetch_instruments

echo "== tests"
$P -W ignore -m pytest -q tests

echo
echo "Ready. Try:  $P -m chorale <a web page or file with MusicXML> --audience"
