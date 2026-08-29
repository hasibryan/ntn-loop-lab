#!/usr/bin/env bash
# Day 0: clone the oran-lab WSL distro into this repository as `ntn-lab`.
#
# The lab is installed inside the repository folder rather than the user's home
# directory, the same constraint the first lab worked under. Cloning rather than
# rebuilding keeps the ns-3 toolchain, the Python virtualenv and the Ollama
# runtime that already work, and costs ~11 GB of disk instead of a day of setup.
#
# Resumable: if the tarball already exists the export is skipped, and a stale
# half-imported distro is unregistered before the import is retried. An import
# that is killed part-way leaves a registry entry in state "Installing" with no
# vhdx behind it, which blocks every later attempt until it is cleared.
set -euo pipefail

TAR_WIN="D:\ntn-loop-lab\wsl\ntn-lab.tar"
TAR_POSIX=/d/ntn-loop-lab/wsl/ntn-lab.tar
DEST_WIN="D:\ntn-loop-lab\wsl\ntn-lab"
DEST_POSIX=/d/ntn-loop-lab/wsl/ntn-lab

if [ -s "${TAR_POSIX}" ]; then
  echo "[1/4] tarball present, skipping export ($(du -h "${TAR_POSIX}" | cut -f1))"
else
  echo "[1/4] exporting oran-lab -> ${TAR_WIN}"
  wsl.exe --export oran-lab "${TAR_WIN}"
fi

# wsl.exe writes UTF-16 with a byte-order mark, so strip nulls and everything that
# is not a name character before matching. Getting this wrong sends the script down
# the "not registered" branch, and the import then fails against the stale entry it
# should have cleared, with Wsl/Service/RegisterDistro/0x8000000d.
if wsl.exe -l -q 2>/dev/null | tr -d '\0\r' | sed 's/[^A-Za-z0-9._-]//g' | grep -qx 'ntn-lab'; then
  if [ -d "${DEST_POSIX}" ]; then
    echo "[2/4] ntn-lab already imported, skipping"
  else
    echo "[2/4] clearing stale ntn-lab registration with no disk image behind it"
    # An import killed part-way leaves the distro in state "Installing" and every
    # later wsl command against it is refused until the service is bounced.
    wsl.exe --shutdown
    wsl.exe --unregister ntn-lab
    echo "[2/4] importing as ntn-lab -> ${DEST_WIN}"
    wsl.exe --import ntn-lab "${DEST_WIN}" "${TAR_WIN}" --version 2
  fi
else
  echo "[2/4] importing as ntn-lab -> ${DEST_WIN}"
  wsl.exe --import ntn-lab "${DEST_WIN}" "${TAR_WIN}" --version 2
fi

echo "[3/4] pointing /opt/ntnlab at the inherited virtualenv"
wsl.exe -d ntn-lab -u root -- sh -c 'ln -sfn /opt/oranlab /opt/ntnlab; /opt/ntnlab/venv/bin/python -c "import numpy, matplotlib; print(\"venv ok, numpy\", numpy.__version__)"'

echo "[4/4] removing the intermediate tarball"
rm -f "${TAR_POSIX}"

echo "done: wsl -d ntn-lab"
