#!/usr/bin/env bash
# make doctor -- is this machine able to run the lab today?
#
# Checks only what a stage actually needs, and says which day needs it, so a red
# line is actionable rather than alarming. Missing Vivado on day 1 is fine.
set -uo pipefail

REPO=/mnt/d/ntn-loop-lab
PY=/opt/ntnlab/venv/bin/python
ok=0; bad=0

check () {  # check "<label>" "<needed by>" "<command>"
  if eval "$3" >/dev/null 2>&1; then
    printf '  \033[32mok\033[0m    %-34s %s\n' "$1" "$2"; ok=$((ok+1))
  else
    printf '  \033[31mmiss\033[0m  %-34s %s\n' "$1" "$2"; bad=$((bad+1))
  fi
}

echo "distro and paths"
check "repository mounted"        "everything"  "test -d $REPO"
check "shared ollama weights"     "day 12"      "test -d $REPO/tools/ollama-models"
check "virtualenv"                "day 1"       "test -x $PY"

echo
echo "python"
for m in numpy scipy matplotlib skyfield sgp4 requests; do
  check "import $m" "day 1-3" "$PY -c 'import $m'"
done
for m in gymnasium stable_baselines3 torch; do
  check "import $m" "day 9-10" "$PY -c 'import $m'"
done
for m in cocotb jsonschema langgraph zmq; do
  check "import $m" "day 6, 12, 4" "$PY -c 'import $m'"
done

echo
echo "toolchains"
check "verilator"                 "day 6"       "command -v verilator"
check "vivado"                    "day 6 synth" "command -v vivado"
check "nvcc"                      "day 7"       "command -v nvcc"
check "srsRAN gnb"                "day 4"       "command -v gnb"
check "open5gs core"              "day 4"       "command -v open5gs-amfd"
check "ollama responds"           "day 12"      "curl -sf http://127.0.0.1:11434/api/tags"

echo
echo "resources"
free -h  | awk '/Mem:/ {printf "  ram   %s total, %s available\n", $2, $7}'
df -h /mnt/d | awk 'NR==2 {printf "  disk  %s free on D:\n", $4}'
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>/dev/null \
  | awk '{printf "  gpu   %s\n", $0}' || echo "  gpu   not visible from this distro"

echo
echo "  $ok present, $bad missing"
[ "$bad" -eq 0 ] || echo "  missing entries are only a problem on the day named beside them"
