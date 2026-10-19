# Validation record

Validated on 2026-10-19 in the cloud, using an isolated **Ubuntu 24.04 noble
x86_64 userspace** with packages authenticated against Ubuntu's signed APT
metadata. The host is Debian 13; PRoot runs the Ubuntu compiler and libraries.
This is userspace build validation, not a running Zorin desktop or USB test.

| Check | Result |
|---|---|
| Full patched libfprint build | Passed; GCC 13.3, GLib 2.80, libgusb 0.4.8, OpenSSL 3.0.13 |
| Built supported-device list includes `047d:00f2` | Passed |
| Kensington C transport suite | 1 Meson test executable passed, containing 5 passing cases |
| Zorin integration tests | 21 passed |
| Upstream Python offline suite | 42 passed, 1 skipped: private capture intentionally not distributed |
| Ubuntu packaged fprintd 1.94.3 dynamic symbol resolution with custom library | Passed; `ldd -r`, no missing libraries or undefined symbols |
| Packaged fprintd `--help` with custom library | Passed |
| Repeat source preparation | Passed; pinned source checksums and pristine dependency revision preserved |
| Native installation/systemd startup on target | Not run |
| Actual pairing/enrollment/match/nonmatch | Not run |
| PAM, sudo, GDM, password fallback | Not run on hardware; integration logic covered with simulated commands |
| GitHub Actions | Workflow added; execution not claimed |

Reproduce the normal build/tests on a Zorin or Ubuntu 24.04 machine:

```bash
sudo scripts/install-deps.sh
scripts/build.sh
scripts/test.sh
```

The tests check refusal of incompatible/tampered artifacts, reader selection,
private-state protection, failed-install recovery, preservation of unrelated
files, password-fallback requirements, PAM ownership, and explicit hardware
verification gates. These are not an end-to-end test of systemd or a desktop
login. The test fixture never authenticates a real user.

The upstream TLS prototype test requires a separate pristine Git dependency;
the patched build source is kept independently. This corrected the initial
test setup failure without altering or skipping the TLS assertion.

Raw Meson logs include inherited environment settings. Keep them local;
share test summaries, not unreviewed logs or USB captures. Device-level
validation remains the next step in [local-handoff.md](local-handoff.md).
