#!/usr/bin/env bash
# Release everything a run holds: the ZMQ ports the NTN shim sits between, the E2
# ports, the NGAP port to the core.
#
# This script exists so that nobody reaches for `pkill -f` with a broad pattern.
# That matches the invoking shell and kills it -- a lesson already paid for once
# in the first lab (tasks/lessons.md 4.1). PIDs are recorded at start; only those
# PIDs are signalled.
set -uo pipefail

RUNDIR=/mnt/d/ntn-loop-lab/data/run
PORTS='2000|2001|36421|36422|38412|11434'

if [ -d "$RUNDIR" ]; then
  for f in "$RUNDIR"/*.pid; do
    [ -e "$f" ] || continue
    pid=$(cat "$f")
    if kill -0 "$pid" 2>/dev/null; then
      echo "stopping $(basename "$f" .pid) (pid $pid)"
      kill -TERM "$pid" 2>/dev/null
    fi
    rm -f "$f"
  done
fi

sleep 2

echo "still bound, if anything:"
ss -ltnp 2>/dev/null | grep -E ":($PORTS) " || echo "  nothing -- ports are clear"
