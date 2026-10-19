# Recovery and private state

The integration never formats storage, updates firmware, detaches HID
interface 0, or automatically deletes sensor templates. A hardware test can
still change persistent pairing/enrollment; preserve existing private state
before experimenting when it exists.

## Interrupted pairing

If `pairing.pending` exists under `/var/lib/fprint/verimark/047d-00f2`, stop.
The reader may have accepted PAIR even if its response was lost. Deleting
pending state and repeating PAIR can discard the only recoverable key.
Keep both the root-only pending file and the capture under
`/var/lib/verimark-zorin/pairing-*/`. Review the pinned upstream
`.build/sources/uriziel/docs/linux/new-linux-pairing.md` and
`pairing-recovery.md` locally. Do not paste private files into chat or commit
them to the repository.

If pairing completed but conversion failed, a subsequent `pair` command
converts `pairing.bin` without sending PAIR again, provided no pending record
remains. Existing `libfprint-persistent.bin` is never overwritten.

## fprintd cannot load the library

The installer restores its previous library/drop-in if startup checks fail.
Read `sudo journalctl -u fprintd -n 80 --no-pager` **locally**, looking for
missing libraries, denied paths, or protocol errors. Avoid sharing raw debug
logs: upstream logs may contain device identifiers. A same-SONAME library
alone does not prove compatibility; the installer also checks symbol
resolution and the loaded process mapping.

If there is a previous driver override from another project, review and
remove that installation using its own rollback instructions first. This
project refuses conflicting overrides instead of deleting them.

After a reboot or interrupted pairing wrapper, fprintd might be masked in
`/run/systemd/system/fprintd.service`. Once no pairing process remains,
inspect it and, if it was created by this test, run:

```bash
sudo systemctl unmask --runtime fprintd.service
sudo systemctl restart fprintd.service
```

## Login fallback

Keep the original terminal open during the first login tests. If fingerprint
authentication is unreliable, disable it using the commands in the README.
If PAM has local customizations and `pam-auth-update` refuses them, inspect
those changes rather than using `--force`. The tool saves the prior
`common-auth` file privately in `/var/lib/verimark-zorin/`; restore it manually
only after checking whether other authentication settings changed since then.

Do not delete `/var/lib/fprint` as a troubleshooting step. It contains pairing
keys and enrollment records, not disposable build output. Before reinstalling
the OS, back it up to encrypted offline storage, retaining root ownership and
permissions. Rollback cannot restore Windows pairing; Windows Hello may need
to be enrolled again.
