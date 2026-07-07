#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[desktop]'
python -m unittest discover -s tests -v

cd frontend
npm ci
npm run test
npm run build
cd ..

python scripts/build_icons.py
python packaging/setup_macos.py py2app --dist-dir dist-macos --bdist-base build-macos

mkdir -p release
rm -f release/Decision-Shelf-macos-apple-silicon.zip
ditto -c -k --sequesterRsrc --keepParent \
  "dist-macos/Decision Shelf.app" \
  "release/Decision-Shelf-macos-apple-silicon.zip"
echo "Created release/Decision-Shelf-macos-apple-silicon.zip"
