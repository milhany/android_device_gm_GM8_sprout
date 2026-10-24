# Bounded launch-window experiment

Branch: `lineage-19.1-launch-test`.
Baseline device commit: `6b90a0f63c65979f3b4671a0efaf5037b8c30be2`.

## Motivation and scope

The October 24 TikTok trace shows an approximately 1.37-second activityStart
slice, a nested 1.02-second performCreate, and a later initial UI frame of
about 1.02 seconds including a 648-ms measure slice. These nested/parallel
durations are not additive. The original 750-ms launch window is short
relative to this startup work. The trace does not prove that extending it
will improve the workload, and the earlier clock-alignment caveats still
apply; see DEXOPT-20261024.md.

Change only the nine existing LAUNCH action durations in powerhint.json from
750 to 2000 ms. All votes expire together, while the framework's LAUNCH-off
event can cancel them sooner. CPU frequency values and available hardware
limits retain the existing values. Interaction, rendering, audio, idle and
battery-saver behavior retain their baseline settings. Existing HAL handling
cancels launch votes on screen-off or battery-saver activation.

This branch also inherits the confirmed speed-profile compilation-scope
correction and all earlier device fixes from lineage-19.1. The launch-window
experiment is kept separate so it can be compared without promoting an
unmeasured performance change to the shipping branch. It may increase energy
use per launch. It does not repair app-owned locking, resource loading or
video buffering, and promises no particular launch time or FPS.

## Build and compare

Use the existing vendor GPU-test checkout, diagnostic kernel and release keys.
Build and sign a full `user` ROM with build-19.1.sh / release-19.1.py. Both
the profile properties and vendor powerhint.json need updating; boot.img alone
does not install this experiment. An update using the existing release keys
does not require Format Data solely for this change.

After installation, check `pm.dexopt.install` and `pm.dexopt.bg-dexopt` are
`speed-profile`, and `/vendor/etc/powerhint.json` has 2000-ms LAUNCH durations.
Keep app version, brightness, network, battery-saver state and charging state
the same. Let the phone return to a comparable temperature before each run.
Record several new-process launches and normal video scrolling; compare launch
times, visible stutter, temperature and energy behavior. Distinguish warm
process launches from new-process launches. No repeated manual compilation is
part of ordinary use.

Check screen-off and battery-saver release behavior on the phone. Host tests
exercise the actual Power/InteractionHandler sources with boundary fixtures;
they do not establish hardware boost timing, thermal behavior or power use.
If launch time or frame pacing does not improve, or energy behavior worsens,
return the device checkout to `lineage-19.1`, rebuild/sign and install the
normal same-key update. Keep the already confirmed profile policy correction.

Validation before publication: JSON action/node/value consistency; exact
nine-duration-only config diff against the baseline; existing power-policy
host test; whitespace checks. Full Android build and phone comparison pending.
