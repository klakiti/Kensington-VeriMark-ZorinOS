#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
set -euo pipefail
source /etc/os-release
if [[ ${UBUNTU_CODENAME:-${VERSION_CODENAME:-}} != noble ]]; then
    echo 'This installer targets Zorin OS 18 / Ubuntu 24.04 (noble).' >&2
    exit 1
fi
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential pkg-config meson ninja-build git curl ca-certificates patch \
    libglib2.0-dev libgusb-dev libssl-dev libcairo2-dev \
    python3 python3-gi python3-cryptography \
    fprintd libpam-fprintd usbutils tcpdump kmod
