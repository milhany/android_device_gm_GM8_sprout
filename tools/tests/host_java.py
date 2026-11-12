"""Select and validate a host Java compiler independently of source fixtures."""
import os
from pathlib import Path
import shutil
import subprocess


def find_java(top, executable=None):
    """Return an absolute java path with a runnable jdk.compiler module.

    The coordinator selects from the real checkout and passes GM8_HOST_JAVA
    to tests whose --top points at a temporary, deliberately JDK-free tree.
    An explicit selection is authoritative: a bad override must fail visibly.
    """
    explicit = executable or os.environ.get('GM8_HOST_JAVA')
    if explicit:
        candidates = [Path(shutil.which(str(explicit)) or explicit)]
    else:
        candidates = [Path(top) / f'prebuilts/jdk/{version}/linux-x86/bin/java'
                      for version in ('jdk11', 'jdk17', 'jdk21')]
        if os.environ.get('JAVA_HOME'):
            candidates.append(Path(os.environ['JAVA_HOME']) / 'bin/java')
        system_java = shutil.which('java')
        if system_java:
            candidates.append(Path(system_java))
        candidates.append(Path('/usr/lib/jvm/default-java/bin/java'))
    failures = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            failures.append(f'{candidate}: missing or not executable')
            continue
        try:
            result = subprocess.run([str(candidate), '-m',
                'jdk.compiler/com.sun.tools.javac.Main', '-version'],
                text=True, capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            failures.append(f'{candidate}: {error}')
            continue
        if result.returncode == 0:
            return str(candidate)
        detail = (result.stderr or result.stdout).strip()[-600:]
        failures.append(f'{candidate}: compiler probe failed ({result.returncode}): {detail}')
    raise RuntimeError('A runnable JDK with jdk.compiler is required for host checks. '
                       'Use the checkout JDK or set GM8_HOST_JAVA to its bin/java.\n'
                       + '\n'.join(failures))
