#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
python3 -m unittest discover -s tests -v
# Use the distro Python so apt-provided cryptography and PyGObject are found.
"${VERIMARK_SYSTEM_PYTHON:-/usr/bin/python3}" -m unittest discover \
    -s .build/sources/uriziel/tests -v
meson test -C .build/driver synatlsmoc-kensington --print-errorlogs
