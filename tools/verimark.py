#!/usr/bin/python3
"""Zorin OS 18 integration for the Kensington VeriMark Desktop (047d:00f2).

SPDX-License-Identifier: LGPL-2.1-or-later
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
LIBDIR = Path('/opt/verimark-zorin/lib')
LIBNAME = 'libfprint-2.so.2.0.0'
DROPIN = Path('/etc/systemd/system/fprintd.service.d/60-verimark-zorin.conf')
STATE = Path('/var/lib/verimark-zorin')
PAMDIR = Path('/etc/pam.d')
PAIRDIR = Path('/var/lib/fprint/verimark/047d-00f2')
PAIRFILE = PAIRDIR / 'libfprint-persistent.bin'
MARKER = '# Managed by Kensington-VeriMark-ZorinOS\n'
DROPIN_TEXT = (MARKER + '[Service]\n'
               f'Environment="LD_LIBRARY_PATH={LIBDIR}"\n'
               f'Environment="SYNA_TLSMOC_PERSISTENT_DATA_FILE={PAIRFILE}"\n')


class SetupError(RuntimeError):
    pass


def run(args, *, check=True, env=None, timeout=60):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=True,
                            timeout=timeout, env=env)
    if check and result.returncode:
        # Commands never include pairing material. Do not dump the journal/environment.
        raise SetupError(f'{args[0]} failed ({result.returncode}): '
                         f'{result.stderr.strip() or result.stdout.strip()}')
    return result


def os_info(path=Path('/etc/os-release')):
    result = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            result[key] = shlex.split(value)[0] if value else ''
    return result


def require_target():
    info = os_info()
    if info.get('ID') not in ('zorin', 'ubuntu') or info.get(
            'UBUNTU_CODENAME', info.get('VERSION_CODENAME')) != 'noble':
        raise SetupError('System changes require Zorin OS 18 / Ubuntu 24.04 (noble).')
    if os.geteuid() != 0:
        raise SetupError('Run this command with sudo /usr/bin/python3.')


def readers(root=Path('/sys/bus/usb/devices')):
    result = []
    if not root.exists():
        return result
    for device in root.iterdir():
        try:
            if ((device / 'idVendor').read_text().strip().lower(),
                    (device / 'idProduct').read_text().strip().lower()) == ('047d', '00f2'):
                result.append(device)
        except FileNotFoundError:
            continue
    return result


def require_reader():
    found = readers()
    if len(found) != 1:
        raise SetupError(f'Connect exactly one 047d:00f2 reader; found {len(found)}.')
    return found[0]


def private_file(path):
    info = path.lstat()
    import stat
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise SetupError(f'{path} must be a root-owned regular file with mode 0600.')
    if info.st_size == 0:
        raise SetupError(f'{path} is empty; restore or create real pairing state.')


def validate_artifact(directory):
    library = directory / LIBNAME
    metadata = json.loads((directory / 'build.json').read_text())
    if metadata.get('codename') != 'noble' or metadata.get('architecture') != platform.machine():
        raise SetupError('Rebuild on this Zorin/Ubuntu noble architecture; this artifact is incompatible.')
    if hashlib.sha256(library.read_bytes()).hexdigest() != metadata.get('sha256'):
        raise SetupError('Library checksum does not match build.json; rebuild before installing.')
    dynamic = run(['readelf', '-d', library]).stdout
    if 'Library soname: [libfprint-2.so.2]' not in dynamic:
        raise SetupError('Unexpected library SONAME.')
    return library


def require_abi(library_dir):
    candidates = [Path('/usr/libexec/fprintd'), Path('/usr/lib/fprintd/fprintd')]
    daemon = next((p for p in candidates if p.is_file()), None)
    if daemon is None:
        raise SetupError('Packaged fprintd is missing; run scripts/install-deps.sh.')
    environment = dict(os.environ, LD_LIBRARY_PATH=str(library_dir), LC_ALL='C')
    result = run(['ldd', '-r', daemon], env=environment, check=False)
    output = result.stdout + result.stderr
    if result.returncode or 'not found' in output or 'undefined symbol' in output:
        raise SetupError('Packaged fprintd is not ABI-compatible with this build: ' + output.strip())
    if str(library_dir / 'libfprint-2.so.2') not in output:
        raise SetupError('ABI check did not resolve the custom libfprint.')


def check_service():
    reply = run(['busctl', '--timeout=20', 'call', 'net.reactivated.Fprint',
                 '/net/reactivated/Fprint/Manager', 'net.reactivated.Fprint.Manager',
                 'GetDevices']).stdout.strip()
    if not re.match(r'^ao [1-9][0-9]* ', reply):
        raise SetupError('fprintd did not discover a reader.')
    pid = run(['systemctl', 'show', '--property=MainPID', '--value', 'fprintd.service']).stdout.strip()
    if not pid.isdigit() or pid == '0':
        raise SetupError('fprintd has no live process.')
    if str(LIBDIR / LIBNAME) not in Path(f'/proc/{pid}/maps').read_text():
        raise SetupError('fprintd loaded a different libfprint library.')


def check_conflicts():
    for directory in (Path('/etc/systemd/system/fprintd.service.d'),
                      Path('/run/systemd/system/fprintd.service.d')):
        for conf in directory.glob('*.conf'):
            if conf != DROPIN and re.search(r'LD_LIBRARY_PATH|SYNA_TLSMOC|LD_PRELOAD', conf.read_text()):
                raise SetupError(f'Existing driver override needs review before installing: {conf}')
    if DROPIN.exists() and DROPIN.read_text() != DROPIN_TEXT:
        raise SetupError(f'Refusing to replace an unfamiliar configuration: {DROPIN}')
    if LIBDIR.exists() and not DROPIN.exists():
        raise SetupError(f'Refusing to replace an unmanaged directory: {LIBDIR}')


def install(directory):
    require_target()
    require_reader()
    private_file(PAIRFILE)
    library = validate_artifact(directory)
    check_conflicts()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The previous installation stays recoverable until startup validation succeeds.
    with tempfile.TemporaryDirectory(prefix='install-', dir=STATE) as temporary:
        backup = Path(temporary)
        if LIBDIR.exists():
            shutil.copytree(LIBDIR, backup / 'lib', symlinks=True)
        if DROPIN.exists():
            shutil.copy2(DROPIN, backup / 'override')
        candidate = backup / 'candidate'
        candidate.mkdir()
        shutil.copy2(library, candidate / LIBNAME)
        (candidate / 'libfprint-2.so.2').symlink_to(LIBNAME)
        require_abi(candidate)
        run(['systemctl', 'stop', 'fprintd.service'])
        try:
            LIBDIR.mkdir(parents=True, exist_ok=True)
            os.chmod(LIBDIR.parent, 0o755)
            os.chmod(LIBDIR, 0o755)
            shutil.copyfile(library, LIBDIR / LIBNAME)
            os.chmod(LIBDIR / LIBNAME, 0o644)
            link = LIBDIR / 'libfprint-2.so.2'
            link.unlink(missing_ok=True)
            link.symlink_to(LIBNAME)
            DROPIN.parent.mkdir(parents=True, exist_ok=True)
            DROPIN.write_text(DROPIN_TEXT)
            os.chmod(DROPIN, 0o644)
            run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'restart', 'fprintd.service'])
            check_service()
        except Exception:
            run(['systemctl', 'stop', 'fprintd.service'], check=False)
            shutil.rmtree(LIBDIR)
            DROPIN.unlink(missing_ok=True)
            if (backup / 'lib').exists():
                shutil.copytree(backup / 'lib', LIBDIR, symlinks=True)
            if (backup / 'override').exists():
                shutil.copy2(backup / 'override', DROPIN)
            run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'restart', 'fprintd.service'], check=False)
            raise
    print('Custom library loaded and reader discovered. Next: enroll and test. PAM is unchanged.')


def pam_has(text, module):
    return any(module in line.split() for line in text.splitlines()
               if line.strip() and not line.lstrip().startswith('#'))


def set_login(enable, username=None, verified=False):
    require_target()
    auth = PAMDIR / 'common-auth'
    marker = STATE / 'pam-enabled-by-verimark'
    before = auth.read_text()
    if not pam_has(before, 'pam_unix.so'):
        raise SetupError('Password fallback is not present in common-auth; review PAM manually.')
    if enable:
        if not verified:
            raise SetupError('First test enrolled-finger match and wrong-finger rejection; then use --verified-match-and-rejection.')
        if not username or username.startswith('-') or username == 'root':
            raise SetupError('Specify your normal login account with --user.')
        run(['id', username])
        if any(pam_has(p.read_text(), 'pam_u2f.so') for p in PAMDIR.iterdir() if p.is_file()):
            raise SetupError('Active pam_u2f rules exist. Review them separately so touch-only authentication cannot bypass fingerprints.')
        require_reader()
        check_service()
        listing = run(['fprintd-list', username], env=dict(os.environ, LC_ALL='C')).stdout
        if not re.search(r'\b(?:left|right)-(?:thumb|index-finger|middle-finger|ring-finger|little-finger)\b', listing):
            raise SetupError('No enrolled fingerprint found for this account.')
        if pam_has(before, 'pam_fprintd.so'):
            print('Fingerprint PAM is already enabled; its ownership remains unchanged.')
            return
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup = STATE / 'common-auth.before-fingerprint'
        if not backup.exists():
            backup.write_text(before)
            backup.chmod(0o600)
        # Write intent before invoking pam-auth-update so interruption remains recoverable.
        marker.write_text('Enabled the packaged fprintd profile.\n')
        marker.chmod(0o600)
    elif not marker.exists():
        print('No fingerprint PAM profile enabled by this tool; nothing to disable.')
        return
    run(['pam-auth-update', '--enable' if enable else '--disable', 'fprintd'],
        env=dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C'))
    after = auth.read_text()
    if not pam_has(after, 'pam_unix.so') or pam_has(after, 'pam_fprintd.so') != enable:
        raise SetupError('PAM update did not produce the expected password/fingerprint configuration. '
                         'Keep the current terminal open and inspect common-auth; do not reboot.')
    if not enable:
        marker.unlink()
    print('Fingerprint login enabled; test password fallback in a new terminal.' if enable
          else 'Fingerprint PAM profile disabled; password fallback remains configured.')


def rollback():
    require_target()
    set_login(False)
    if not DROPIN.exists():
        print('No managed driver override installed.')
        return
    if DROPIN.read_text() != DROPIN_TEXT:
        raise SetupError('Override was edited; review it before removing it.')
    run(['systemctl', 'stop', 'fprintd.service'])
    DROPIN.unlink()
    # Remove only files owned by this project. Pairing and enrollments stay intact.
    for name in (LIBNAME, 'libfprint-2.so.2'):
        (LIBDIR / name).unlink(missing_ok=True)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'restart', 'fprintd.service'])
    for directory in (LIBDIR, LIBDIR.parent):
        try:
            directory.rmdir()
        except OSError:
            pass
    print('Packaged libfprint restored. Private pairing and fingerprints retained.')


def pair(accepted):
    require_target()
    if not accepted:
        raise SetupError('Pairing replaces the reader\'s Windows pairing. Use --accept-windows-pairing-loss to proceed.')
    device = require_reader()
    upstream = REPO / '.build/sources/uriziel/tools'
    if not (upstream / 'verimark_pair.py').is_file():
        raise SetupError('Run scripts/build.sh first.')
    PAIRDIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (PAIRDIR, PAIRDIR.parent, PAIRDIR.parent.parent):
        if path.is_symlink() or path.stat().st_uid != 0:
            raise SetupError('Pairing directory ancestry must be root-owned and not symlinked.')
    PAIRDIR.chmod(0o700)
    if PAIRFILE.exists() or PAIRFILE.is_symlink():
        private_file(PAIRFILE)
        print('Existing persistent pairing retained; no USB pairing performed.')
        return
    if (PAIRDIR / 'pairing.pending').exists():
        raise SetupError('An interrupted pairing exists. Follow docs/recovery.md; do not pair again.')
    if (PAIRDIR / 'pairing.bin').exists():
        run(['/usr/bin/python3', upstream / 'verimark_libfprint_pairing.py', '--convert',
             '--approval-token', 'IMPORT_EXISTING_PAIRING_FOR_LIBFPRINT'])
        print('Converted the existing pairing without opening USB.')
        return
    status = run(['systemctl', 'is-enabled', 'fprintd.service'], check=False).stdout.strip()
    if status.startswith('masked'):
        raise SetupError('fprintd is already masked; resolve that configuration before pairing.')
    run(['modprobe', 'usbmon'])
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    capture_dir = Path(tempfile.mkdtemp(prefix='pairing-', dir=STATE))
    capture = capture_dir / 'capture.pcap'
    capture.touch(mode=0o600)
    bus = int((device / 'busnum').read_text())
    capture_process = None
    was_active = run(['systemctl', 'is-active', '--quiet', 'fprintd.service'], check=False).returncode == 0
    run(['systemctl', 'mask', '--runtime', '--now', 'fprintd.service'])
    try:
        with (capture_dir / 'tcpdump.log').open('w') as log:
            capture_process = subprocess.Popen(
                ['tcpdump', '-Z', 'root', '-i', f'usbmon{bus}', '-U', '-s', '0', '-w', str(capture)],
                stdout=log, stderr=log)
            for _ in range(40):
                if capture_process.poll() is not None:
                    raise SetupError(f'USB capture failed; see private log in {capture_dir}.')
                if capture.stat().st_size >= 24:
                    break
                time.sleep(0.1)
            else:
                raise SetupError('USB capture did not become ready; pairing was not attempted.')
            run(['/usr/bin/python3', upstream / 'verimark_pair.py', '--execute-new-pairing',
                 '--accept-windows-loss', '--approval-token', 'NEW_LINUX_PAIRING_ONCE',
                 '--capture-file', capture], timeout=90)
            run(['/usr/bin/python3', upstream / 'verimark_libfprint_pairing.py', '--convert',
                 '--approval-token', 'IMPORT_EXISTING_PAIRING_FOR_LIBFPRINT'])
    finally:
        if capture_process is not None and capture_process.poll() is None:
            capture_process.send_signal(signal.SIGINT)
            try:
                capture_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture_process.kill()
                capture_process.wait()
        run(['systemctl', 'unmask', '--runtime', 'fprintd.service'])
        if was_active:
            run(['systemctl', 'start', 'fprintd.service'])
    private_file(PAIRFILE)
    print(f'Pairing saved privately. Sensitive USB capture retained in {capture_dir}; never upload it.')


def doctor():
    info = os_info()
    print(f"OS: {info.get('PRETTY_NAME', 'unknown')}; architecture: {platform.machine()}")
    found = readers()
    print(f'Readers matching 047d:00f2: {len(found)}')
    print(f'Managed fprintd override: {"present" if DROPIN.exists() else "absent"}')
    print('Pairing state: ' + ('present' if PAIRFILE.exists() else 'absent or not readable as this user'))
    for device in found:
        hid = device.parent / (device.name + ':1.0') / 'driver'
        biometric = device.parent / (device.name + ':1.1') / 'driver'
        print(f'Interface 0: {hid.resolve().name if hid.exists() else "unbound"}')
        print(f'Interface 1: {biometric.resolve().name if biometric.exists() else "unbound (expected)"}')
    # Read-only sysfs/filesystem diagnostics: do not open the sensor or activate fprintd.
    return 0 if len(found) == 1 else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Read-only platform and USB diagnostics')
    install_parser = commands.add_parser('install', help='Install reversible fprintd override; leave PAM alone')
    install_parser.add_argument('--artifact', type=Path, default=REPO / '.build/dist')
    pair_parser = commands.add_parser('pair', help='Create one explicit Linux pairing, or reuse existing state')
    pair_parser.add_argument('--accept-windows-pairing-loss', action='store_true')
    login = commands.add_parser('enable-login', help='Enable the packaged Ubuntu fingerprint PAM profile')
    login.add_argument('--user', required=True)
    login.add_argument('--verified-match-and-rejection', action='store_true')
    commands.add_parser('disable-login')
    commands.add_parser('rollback', help='Restore packaged libfprint; retain private state')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'install':
            install(args.artifact.resolve())
        elif args.command == 'pair':
            pair(args.accept_windows_pairing_loss)
        elif args.command == 'enable-login':
            set_login(True, args.user, args.verified_match_and_rejection)
        elif args.command == 'disable-login':
            set_login(False)
        elif args.command == 'rollback':
            rollback()
    except (SetupError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
