# Continue on the Zorin PC

The user authorized creating a test environment on the target PC and chose
to continue with Codex running locally. The cloud session has not executed
anything on that PC. Reading another Codex chat does not provide its terminal.

Open a local clone of this repository in Codex. Read README.md and this file,
inspect the local working tree, and preserve existing user changes. Use a
dedicated directory for the clone/build; no worktree is needed. Keep all device
private state outside the repository.

Context already established by the local “Kensington VeriMark fingerprint” chat:

- Zorin OS 18.1, Ubuntu noble, x86_64.
- Kensington VeriMark Desktop, USB `047d:00f2`.
- fprintd 1.94.3 and libpam-fprintd already installed.
- Packaged libfprint `1:1.94.7+tod1-0ubuntu5~24.04.8` found no reader.
- HID interface 0 is the CTAP1/U2F touch interface; do not use it as proof of
  fingerprint matching or detach its kernel driver.

Start with build/tests/doctor from the README. Then proceed through explicit
pairing, reversible fprintd integration, and interactive validation. The user
will need to touch the reader for enrollment and verification. Before first
pairing, explain that existing Windows Hello pairing can be invalidated and
establish whether the user needs to preserve it. The general permission to
create a test environment is already given; do not ask for that permission again.

Do not enable PAM simply because installation or enrollment succeeded.
Record these observations from the actual target:

| Check | Status |
|---|---|
| Native build and offline tests on target | Pending |
| Existing pairing backed up if present; first-pairing consequence resolved | Pending |
| fprintd loads custom library and discovers the reader | Pending |
| Enrollment completes | Pending |
| Enrolled finger gives verify-match | Pending |
| Never-enrolled finger gives verify-no-match | Pending |
| Cancellation followed by successful verification | Pending |
| Unplug/reconnect and service restart preserve enrollment | Pending |
| Password works in a new terminal after enabling the packaged PAM profile | Pending |
| Lock-screen fingerprint and password both work | Pending |
| Rollback restores packaged library without deleting private state | Pending |

Report actual evidence and revise the implementation if needed. Cloud tests
are not a substitute for these hardware and authentication checks.
