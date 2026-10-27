# GM8 one-command user release build

On `ilhan@ubuntu` or `builder@gm8-build`, run:

```sh
bash ~/android/lineage-19.1/device/gm/GM8_sprout/tools/build-release-19.1.sh
```

On the host it starts the existing `gm8-build` container and enters as `builder`
with a terminal. It uses the existing host Android bind mount. It does not create
a replacement container, install packages, sync repositories or change branches.
The build uses the currently checked-out device, vendor and kernel sources.

The workflow checks for SDK 32, repo and the existing release key pair, takes a
nonblocking build lock, and removes only allowlisted kernel/DTB/boot outputs and
the previous target-files packaging directory. Kernel sources, Android object
files outside this list, ccache and prior signed releases are retained. Symlinked
cleanup paths and nonstandard OUT_DIR settings are rejected. Do not run a second
manual build in the same source checkout at the same time.

It runs `build-19.1.sh target-files user`, including the compatibility patches,
preflight, `m nothing`, target-files and otatools at `-j32`. It then signs and
verifies the new archive using `~/android/gm8-signing/keys`. Update mode requires
every APK/container/APEX payload key to exist: it never creates replacement
keys. Missing keys stop the workflow. Existing clean-install signing behavior is
still available through `release-19.1.py prepare --install-mode clean`.

If the original keys have a password, enter it at the prepare and sign prompts.
For unencrypted PK8 keys press Enter. Passwords use `/dev/tty`, are not command
arguments or log contents, and are not stored for future builds.

Each run has its own UTC timestamp/random suffix below `~/android/gm8-release/`:

| File | Purpose |
| --- | --- |
| `gm8-19.1-user-release.zip` | Verified signed full A/B OTA |
| `gm8-19.1-user-release-boot.img` | Matching boot image |
| `signed-target_files.zip` | Signed release archive |
| `release-verification.json` | Signature checks and update policy |
| `public-key-map.json` | Public signing identities; no private keys |
| `SHA256SUMS` | OTA and boot checksums |
| `build.log` | This run's build/sign output |

`~/android/gm8-release/latest/` is updated only after signing and verification
finish successfully. A failed build keeps the previous successful `latest`.
It may leave partial files in its timestamped directory; these are not releases.
The original unsigned target-files remain in `out/target/product/GM8_sprout/`.
They are regenerated at the next workflow invocation.

This is an update package for an installed ROM using the **same original keys**,
not a key-migration mechanism. The host tool does not inspect the installed
phone's signing identity. It requests no Format Data and generates no wipe OTA.
It never flashes a phone. Verified signing does not establish hardware stability;
the memory/graphics/power candidate still needs device testing.
