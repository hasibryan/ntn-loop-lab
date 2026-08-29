# Shortcuts for the NTN loop lab. Run these inside the cloned distro:
#
#   wsl -d ntn-lab
#   cd /mnt/d/ntn-loop-lab
#   make doctor
#
# Every target is a thin wrapper around a script in scripts/ or a module in this
# repository. Nothing here hides a step; each target is one stage of the
# fourteen-day plan in tasks/todo.md, and each one ends in a committed figure or
# a measured number.

PY    := /opt/ntnlab/venv/bin/python -u
BAND  ?= s              # s | ka   -- the analytical secondary is Ka
SCS   ?= 30             # kHz, subcarrier spacing for the delay sweep
SEED  ?= 1

.PHONY: help doctor orbit antenna satnogs-fetch doppler-fit ranlink-up delay-sweep \
        rtl-test rtl-synth cuda-bench ric-up rl-train rl-eval loop-latency \
        rapp-bench experiment figures paper all stop

help:
	@echo "setup"
	@echo "  make doctor         toolchain, distro, GPU, Ollama, disk"
	@echo "  make stop           release anything still holding a lab port"
	@echo ""
	@echo "week 1 -- physics, link, silicon"
	@echo "  make orbit          D1  SGP4 pass -> Doppler, Doppler rate, delay, required loop periods"
	@echo "  make antenna        D2  8x8 URA, hybrid 64x4, quantised phase, SINR(t) under adjacent-beam interference"
	@echo "  make satnogs-fetch  D3  pull the pinned real passes from the SatNOGS archive"
	@echo "  make doppler-fit    D3  track the carrier, fit against SGP4, report RMS error in Hz"
	@echo "  make ranlink-up     D4  srsRAN gNB + Open5GS + UE over ZMQ through the NTN shim"
	@echo "  make delay-sweep    D5  one-way delay 0-15 ms; find where RACH and HARQ break (SCS=15|30)"
	@echo "  make rtl-test       D6  cocotb + Verilator, CORDIC NCO and beamformer vs the Python golden model"
	@echo "  make rtl-synth      D6  Vivado synthesis for xc7z020; LUT/DSP/BRAM/Fmax"
	@echo "  make cuda-bench     D7  batched 4x4 Cholesky MMSE, nvcc -arch=sm_50, vs cuSOLVER and NumPy"
	@echo ""
	@echo "week 2 -- the control loops"
	@echo "  make ric-up         D8  FlexRIC, or the mini-RIC fallback; E2 setup and KPM indications"
	@echo "  make rl-train       D9  PPO on the offline orbit environment"
	@echo "  make rl-eval        D10 against max-RSRP, elevation-greedy, tuned hysteresis and the DP oracle"
	@echo "  make loop-latency   D11 live xApp over E2: indication -> decision -> control ACK distribution"
	@echo "  make rapp-bench     D12 intent -> schema-validated A1 policy over the 60-intent benchmark"
	@echo ""
	@echo "results"
	@echo "  make experiment     D13 three arms, same seed"
	@echo "  make figures        D13 regenerate every figure, including the timescale map"
	@echo "  make paper          D14 build the four-page workshop paper"
	@echo "  make all            everything above, from clean"

doctor:
	@bash scripts/status.sh

stop:
	@bash scripts/stop_lab.sh

orbit:
	@$(PY) -m orbit.pass_profile --band $(BAND)

antenna:
	@$(PY) -m antenna.beams --band $(BAND)

satnogs-fetch:
	@$(PY) -m satnogs.fetch --manifest satnogs/manifest.json

doppler-fit:
	@$(PY) -m satnogs.doppler_fit

ranlink-up:
	@bash scripts/run_ranlink.sh

delay-sweep:
	@SCS=$(SCS) bash scripts/delay_sweep.sh

rtl-test:
	@$(MAKE) -C accel/rtl sim

rtl-synth:
	@$(MAKE) -C accel/rtl synth

cuda-bench:
	@$(MAKE) -C accel/cuda bench

ric-up:
	@bash scripts/run_ric.sh

rl-train:
	@SEED=$(SEED) $(PY) -m xapp.train

rl-eval:
	@$(PY) -m xapp.evaluate --baselines rsrp,elevation,hysteresis,oracle

loop-latency:
	@$(PY) -m xapp.latency_probe

rapp-bench:
	@$(PY) -m rapp.benchmark --intents rapp/intents

experiment:
	@bash scripts/experiment.sh

figures:
	@$(PY) -m eval.make_figures

paper:
	@$(MAKE) -C paper

all: orbit antenna satnogs-fetch doppler-fit delay-sweep rtl-test cuda-bench \
     rl-train rl-eval loop-latency rapp-bench experiment figures paper
