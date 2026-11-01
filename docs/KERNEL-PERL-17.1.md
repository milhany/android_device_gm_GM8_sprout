# Kernel module signing on the Q build host

The GM8 3.18 Makefile used a literal `perl` for `mod_sign_cmd`, ignoring
the existing device flag selecting `/usr/bin/env -u PERL5LIB /usr/bin/perl`.
Lineage's kernel build prepends its old Perl binary/libraries to the environment;
that interpreter cannot load Getopt::Std on the Ubuntu 22.04 build container.

Use `$(PERL)` in the module signing command, as other kernel Perl helpers do.
This preserves module signing, key/hash selection and module verification.
The device still selects system Perl and removes only the incompatible PERL5LIB.
No kernel configuration or phone runtime policy is changed.

The 17.1 build entry point now checks FileHandle, IPC::Open2 and Getopt::Std
with that same system interpreter before compiling. If the complete `perl`
package is missing, install it inside the existing container, from the Ubuntu
Docker host:

```bash
sudo docker exec --user root gm8-build bash -lc 'apt-get update && apt-get install -y perl kmod'
```

Refresh both the device and kernel 17.1 branches, then rerun
`tools/build-release-17.1.sh`. Preserve the incremental build outputs and keys.
Copy the updated `configs/gm8-17.1.xml` into `.repo/local_manifests/` if using
that manifest, so a future sync retains the corrected kernel revision.

`python3 device/gm/GM8_sprout/tools/tests/kernel_perl_17_1_test.py` exercises
the real module signing command and unchanged sign-file with real OpenSSL
keys and a synthetic module. The legacy PATH interpreter is deliberately
broken and PERL5LIB deliberately poisoned. The test verifies the appended
RSA/SHA-256 signature cryptographically. It is not a full Android build or
a test of loading kernel modules on a phone.
