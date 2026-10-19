#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
for tool in git curl tar sha256sum patch gcc g++ meson ninja pkg-config; do
    command -v "$tool" >/dev/null || { echo "Missing $tool; run sudo scripts/install-deps.sh" >&2; exit 1; }
done
for dependency in glib-2.0 gio-unix-2.0 gusb openssl cairo; do
    pkg-config --exists "$dependency" || { echo "Missing development dependency: $dependency" >&2; exit 1; }
done
scripts/prepare.sh
source_dir="$repo/.build/sources/synatudor/libfprint/libfprint"
build_dir="$repo/.build/driver"
options=(-Ddrivers=synatlsmoc -Dgtk-examples=false -Ddoc=false -Dintrospection=false
         -Dinstalled-tests=false -Dudev_rules=disabled -Dudev_hwdb=disabled)
if [[ -f $build_dir/build.ninja ]]; then
    meson setup --reconfigure "$build_dir" "$source_dir" "${options[@]}"
else
    meson setup "$build_dir" "$source_dir" "${options[@]}"
fi
meson compile -C "$build_dir" -j "${VERIMARK_JOBS:-4}"
meson test -C "$build_dir" synatlsmoc-kensington --print-errorlogs
"$build_dir/libfprint/fprint-list-supported-devices" > .build/supported-devices.txt
grep -q '047d:00f2' .build/supported-devices.txt
mkdir -p .build/dist
cp "$build_dir/libfprint/libfprint-2.so.2.0.0" .build/dist/
python3 - <<'PY'
import hashlib, json, platform, shlex
from pathlib import Path
os_info = {}
for line in Path('/etc/os-release').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        os_info[key] = shlex.split(value)[0] if value else ''
library = Path('.build/dist/libfprint-2.so.2.0.0')
Path('.build/dist/build.json').write_text(json.dumps({
    'sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
    'architecture': platform.machine(),
    'os_id': os_info['ID'],
    'codename': os_info.get('UBUNTU_CODENAME', os_info.get('VERSION_CODENAME')),
    'source_commit': '5452637c1f67fb35b859571ffd5b594f9225d08f',
    'patch_sha256': 'dddce7ea4e647cfd7585db822082fcf156f243e8fb69bef30fbd71dbeffaaab1',
}, indent=2) + '\n')
PY
echo 'Built and tested .build/dist/libfprint-2.so.2.0.0. No system installation performed.'
