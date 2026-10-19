#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
mkdir -p .build/downloads .build/sources

fetch_source() {
    local name=$1 url=$2 digest=$3 archive=".build/downloads/$1.tar.gz"
    local target=".build/sources/$1"
    if [[ ! -f $archive ]]; then
        curl --fail --location --retry 2 --proto '=https' --tlsv1.2 "$url" -o "$archive.partial"
        printf '%s  %s\n' "$digest" "$archive.partial" | sha256sum --check --status
        mv "$archive.partial" "$archive"
    fi
    printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
    if [[ -d $target ]]; then
        (cd "$target" && sha256sum --check --quiet .source-sha256)
        return
    fi
    local staging
    staging=$(mktemp -d .build/sources/.extract-XXXXXX)
    tar --extract --gzip --file "$archive" --directory "$staging" --strip-components=1 --no-same-owner
    if [[ $name == synatudor ]]; then
        local patch_file="$repo/.build/sources/uriziel/patches/0001-Add-Kensington-VeriMark-Match-in-Sensor-support.patch"
        printf '%s  %s\n' dddce7ea4e647cfd7585db822082fcf156f243e8fb69bef30fbd71dbeffaaab1 "$patch_file" | sha256sum --check --status
        (cd "$staging" && patch --batch --fuzz=0 -p1 < "$patch_file")
    fi
    (cd "$staging" && find . -type f ! -name .source-sha256 -print0 | sort -z | xargs -0 sha256sum > .source-sha256)
    mv "$staging" "$target"
}

fetch_source uriziel \
    https://codeload.github.com/Uriziel01/kensington-verimark-desktop-linux/tar.gz/ffea8f6d4e9bf1c52b3559250e8f5b0665fa693c \
    f4a8e8786db6af5246eb054fa016d9ff5be5e50c337c8c1e207aa150c293159e
fetch_source synatudor \
    https://codeload.github.com/vojtapl/synaTudorMiS/tar.gz/5452637c1f67fb35b859571ffd5b594f9225d08f \
    71c8c4a655eef1adf13ec0e989cb3f8a6154de06aaf5525d72ba064faf41898f

# The upstream TLS tests require a pristine, pinned Git checkout. Keep this
# dependency separate from the patched archive used for the C library.
base_commit=5452637c1f67fb35b859571ffd5b594f9225d08f
pristine="$repo/.build/upstream/synaTudorMiS"
if [[ ! -d $pristine ]]; then
    mkdir -p "$pristine"
    git -C "$pristine" init --quiet
    git -C "$pristine" remote add origin https://github.com/vojtapl/synaTudorMiS.git
fi
if ! git -C "$pristine" rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "$pristine" fetch --depth=1 origin "$base_commit"
    git -C "$pristine" checkout --detach "$base_commit"
fi
[[ $(git -C "$pristine" rev-parse HEAD) == "$base_commit" ]]
[[ -z $(git -C "$pristine" status --porcelain) ]] || {
    echo 'Pristine test dependency has local changes; refusing to overwrite them.' >&2
    exit 1
}
# The unchanged upstream pairing tool also locates public protocol keys here.
mkdir -p .build/sources/uriziel/upstream
link=.build/sources/uriziel/upstream/synaTudorMiS
if [[ ! -e $link && ! -L $link ]]; then
    ln -s ../../../upstream/synaTudorMiS "$link"
fi
[[ $(readlink -f "$link") == "$pristine" ]]
echo 'Pinned sources and Kensington patch verified.'
