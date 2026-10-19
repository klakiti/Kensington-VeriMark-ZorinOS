# Kensington VeriMark Desktop on Zorin OS 18

Experimental native fingerprint support for the **Kensington VeriMark Desktop
(`047d:00f2`, K62330WW)** on **Zorin OS 18 / Ubuntu 24.04 (noble)**.
It uses sensor-side biometric matching through libfprint and fprintd. The
reader's separate U2F touch interface is not used to authenticate a fingerprint.

**Status:** the driver builds in an Ubuntu 24.04 userspace and offline tests
pass. Enrollment, rejection of unregistered fingers, and login on the target
Zorin PC still require hardware validation. See [validation](docs/validation.md).

This project adapts the shared `synatlsmoc` implementation used by
[SShadowS/verimark-linux-driver](https://github.com/SShadowS/verimark-linux-driver/tree/1239ab8272b4cd53a62065d855fbfb328176d0f7/synatlsmoc)
and
[Uriziel01/kensington-verimark-desktop-linux](https://github.com/Uriziel01/kensington-verimark-desktop-linux/tree/ffea8f6d4e9bf1c52b3559250e8f5b0665fa693c).
The protocol driver is reused, not reimplemented. Read [provenance](docs/provenance.md)
for pinned versions and design decisions.

## Where to run this

Run these commands **locally on the Zorin PC with the USB reader attached**.
A GitHub repository is central code storage; a Codex cloud environment is a
separate computer and cannot see your local USB reader. Open a local clone in
Codex to develop and test on the same PC. No kernel driver, DKMS module, or
Secure Boot change is required.

## Build and check without changing login

From the repository directory:

```bash
sudo scripts/install-deps.sh
scripts/build.sh
scripts/test.sh
/usr/bin/python3 tools/verimark.py doctor
```

Build as your normal user. Sources are pinned by commit and archive/patch
SHA-256; dependencies and output stay in the ignored `.build/` directory.
The build is repeatable and refuses to overwrite modified dependency files.
`doctor` reads sysfs and configuration presence without opening the sensor.
Exit status 2 means exactly one matching reader was not found.

## Pair with Linux

**This changes the reader's host pairing and can invalidate Windows Hello
pairing and stored fingerprints.** It is a distinct operation, never an
automatic consequence of driver installation or a diagnostic command. If you
already use this reader with Windows, decide whether losing that pairing is
acceptable before proceeding.

Close fingerprint settings and other applications using the reader. Connect
the reader directly if possible, then run:

```bash
sudo /usr/bin/python3 tools/verimark.py pair --accept-windows-pairing-loss
```

This wraps Uriziel01's bounded pairing tool, checks returned certificates,
retains pending state after an interrupted attempt, and writes root-owned
mode-0600 pairing data under `/var/lib/fprint/verimark/047d-00f2/`. Existing
complete pairing is reused. A root-only USB capture is retained under
`/var/lib/verimark-zorin/` for recovery; it can include other traffic on that
USB bus. Never upload it, pairing files, or `/var/lib/fprint` to GitHub.
There is no automatic retry or reset. See [recovery](docs/recovery.md) if this fails.

## Install and validate the reader

```bash
sudo /usr/bin/python3 tools/verimark.py install
fprintd-enroll -f right-index-finger "$USER"
fprintd-verify -f right-index-finger "$USER"
```

The installer validates the build's architecture, Ubuntu release, checksum,
SONAME, and compatibility with packaged fprintd. It installs only under
`/opt/verimark-zorin/` and an individually named systemd drop-in. The packaged
library and service command stay in place. Startup must load the intended
library and discover the reader; failure restores the previous installation.
Only the `synatlsmoc` family is built, so other fingerprint-reader families
will not be available while this override is active.

Before enabling login:

1. Verify the enrolled finger returns **`verify-match`**.
2. Run verification again using a finger never enrolled on the reader. It
   must return **`verify-no-match`**. A transport error or timeout is not a
   successful rejection test. Do not rely on the command's exit code alone.
3. Cancel a waiting verification, then verify again successfully.
4. Unplug/reconnect the reader and restart fprintd. Verify the same finger
   without creating a new pairing or enrollment.

Record actual results in [the hardware checklist](docs/local-handoff.md).

## Enable login after those checks

Keep a working terminal and password available:

```bash
sudo /usr/bin/python3 tools/verimark.py enable-login \
  --user "$USER" --verified-match-and-rejection
```

This uses Ubuntu's packaged `pam-auth-update` fingerprint profile. It checks
for a real enrollment, requires password authentication to remain configured,
and refuses active `pam_u2f` rules that need separate review. It does not copy
Fedora's `authselect` configuration onto Zorin or rewrite GDM files.

In a **new terminal**, run `sudo -k; sudo true` and test the enrolled finger.
Repeat and wait for the fingerprint attempt to expire, then enter your password.
Finally test both fingerprint and password at the lock screen before rebooting.
Fingerprint authentication does not unlock a password-encrypted GNOME keyring
or an encrypted disk at boot; those may still require your password.

## Roll back

```bash
sudo /usr/bin/python3 tools/verimark.py disable-login
sudo /usr/bin/python3 tools/verimark.py rollback
```

Rollback removes this project's override and library, restores packaged
libfprint, and retains private pairing and enrollments. It disables only a
fingerprint PAM profile enabled by this tool. It does not undo pairing changes
on the reader or restore Windows Hello; use Windows setup for that.

After an OS/fprintd update, rebuild locally and reinstall if necessary. Do
not re-pair just because software changed. See [recovery](docs/recovery.md).

## License

LGPL-2.1-or-later; see [LICENSE](LICENSE). Upstream code retains its original
notices. No proprietary Windows driver, prebuilt upstream binary, biometric
template, or user pairing secret is included in this repository.
