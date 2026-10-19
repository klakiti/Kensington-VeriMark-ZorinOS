# Source selection

Both requested projects were inspected at these commits:

| Project | Revision | Used for |
|---|---|---|
| SShadowS/verimark-linux-driver | `1239ab8272b4cd53a62065d855fbfb328176d0f7` | Its newer `synatlsmoc/` integration, native build pattern, and comparison with the older clean-room driver |
| Uriziel01/kensington-verimark-desktop-linux | `ffea8f6d4e9bf1c52b3559250e8f5b0665fa693c` | Shared Kensington C patch, guarded pairing/conversion tools, offline tests, recovery evidence |
| vojtapl/synaTudorMiS | `5452637c1f67fb35b859571ffd5b594f9225d08f` | Base libfprint/synatlsmoc source, protocol keys, and TLS reference tests |

SShadowS's newer implementation incorporates the same Uriziel01 Kensington
patch. Combining these two implementations does not require stacking two
different drivers. This project builds that common backend with Ubuntu
packages and uses a Zorin-specific integration layer.

The upstream Kensington patch SHA-256 is
`dddce7ea4e647cfd7585db822082fcf156f243e8fb69bef30fbd71dbeffaaab1`.
Archive SHA-256 values and exact download URLs are in `scripts/prepare.sh`.

We retain Uriziel01's explicit pairing behavior. SShadowS's additional
`0002-verimark-self-pairing.patch` automatically replaces pairing when state
is missing; it is deliberately not applied. Losing a host-side file should
not silently change the reader's Windows pairing.

The old standalone `verimark` driver and Fedora prebuilt shared object are
not used. Neither project provides a verified Zorin 18 installer; the new
packaging checks Ubuntu compatibility, preserves the vendor library, and
uses `pam-auth-update` for the optional login step.

No Ghidra/REA reverse engineering was needed for the implemented path.
Hardware evidence from upstream is useful context, not proof that this
particular user's device and OS combination has passed.
