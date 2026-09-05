# NTN loop lab — fourteen-day plan

> **Deferred at day 2 on 2026-08-28.** Days 0 to 2 are done and committed. Days 3 to 14 are on
> hold behind [`oran-kpm-guard`](https://github.com/hasibryan/oran-kpm-guard), which builds the real E2 interface this
> plan's millisecond tier needs. The reason is in the README: days 8 to 11 here would otherwise
> measure a self-built RIC speaking JSON over TCP, and report the emulator's latency as O-RAN's.
> Nothing below is retracted; the day-1 and day-2 results stand and the open items are still open.

## The question

In a LEO non-terrestrial network the control loops that keep a link alive span seven orders
of magnitude in time: microseconds for Doppler pre-compensation, milliseconds for beam and
satellite selection, seconds for policy. O-RAN assigns these to three places — L1, the
Near-RT RIC, the Non-RT RIC. **Does that assignment survive a cell moving at 7.5 km/s?
Where does it break, and what has to move?**

Everything in this repository exists to answer that one question. A component that does not
feed the answer is not in scope, however good it would look on its own.

## The headline result

**Figure 0 — the timescale map.** Required loop period, derived from orbital dynamics on
day 1, against measured loop latency, instrumented on days 6, 7, 11 and 12. Log-log, with
the infeasible region shaded. Every other figure supports this one.

The expected shape of the answer, to be confirmed or refuted by measurement: at S-band the
Near-RT RIC tier fits comfortably; at Ka-band the Doppler rate is roughly fourteen times
higher and the tier does not. If that holds, it is a statement about where O-RAN's
functional split has to change for NTN, and it is measured rather than asserted.

## Machine constraints that shape the plan

| Resource | Actual | Consequence |
|---|---|---|
| GPU | GeForce 930MX, 2 GB, compute 5.0 | No vLLM (needs 7.0+), no TensorRT (Maxwell dropped). CUDA 12.x, hand-written kernels, `nvcc -arch=sm_50`. |
| RAM | 7.9 GB | srsRAN + Open5GS + RIC and Vivado never run on the same day. No 7B model. |
| CPU | i7-8550U, 4c/8t, 15 W | ZMQ RF at 10 MHz, not 100. PPO on a small MLP, on CPU. |
| Disk | D: 911 GB free | Vivado fits. |
| Radio | none purchased | Real-capture work uses the SatNOGS archive and network. |

## Rules carried over from the first lab

1. Every number in the repository is measured. No estimate is written as if it were a result.
2. A negative result is reported and explained, not tuned away.
3. Claims about standards compliance are checked against the source before they are written.
4. Each day ends with something committed: a figure, a measured number, or a documented failure.

---

## Day 0 — scaffold

- [x] Create the directory tree under `D:\ntn-loop-lab`
- [x] Clone the `oran-lab` WSL distro as `ntn-lab` (`scripts/clone_distro.sh`)
- [x] Junction the Ollama binary and GGUF weights from the first lab rather than copying ~2 GB
- [x] Write `Makefile`, `requirements.txt`, `.gitignore`
- [x] Author the three project skills: `ntn-run`, `rtl-hdl`, `paper-figures`
- [ ] `git init` and first commit
- [ ] `make doctor` passes: distro up, venv imports numpy/scipy/skyfield, nvcc present, Ollama answers
- [ ] **Verify before writing anything about it:** does srsRAN Project implement any Rel-17 NTN
      feature (K_offset, ephemeris-assisted common TA, cell-specific timing offset)? Does
      OpenAirInterface? Record the answer with a citation in `tasks/lessons.md`. The plan
      assumes srsRAN does not, and treats that as the experiment rather than a defect.

---

## Week 1 — physics, link, silicon

### Day 1 — orbit, channel, and the loop-rate requirement

**Done.** `make orbit`, 29 tests in `tests/test_orbit.py` and `tests/test_antenna.py`.

- [x] Closed-form circular-orbit pass model, no dependencies, every quantity checkable by hand
- [x] `orbit/geometry.py::tle_pass` for skyfield/SGP4 propagation — written, exercised on day 3
      when a real recorded pass gives it something to propagate
- [x] Doppler, Doppler rate and one-way delay time series
- [x] Path loss: free space plus gaseous absorption and a scintillation model
- [x] **The load-bearing derivation:** required correction period per band per subcarrier spacing
- [x] Artefacts: `data/ntn_channel_{s,ka}.npz`, `data/orbit_summary.json`, Figure 1

**The plan's anchors were wrong and the model corrected them** (`tasks/lessons.md` 1.1). Not
±48 kHz and 640 Hz/s but:

| | S-band 2 GHz | Ka-band 28 GHz |
|---|---|---|
| peak Doppler, 10 deg mask | 45.40 kHz | 635.65 kHz |
| peak Doppler rate | 581.0 Hz/s | 8134.7 Hz/s |
| CFO update period, 15 kHz SCS | 516 ms | 36.9 ms |
| CFO update period, 30 kHz SCS | 1033 ms | 73.8 ms |

Slant range at 10 degrees 1932 km, one-way delay 6.44 ms, round trip 12.89 ms — matching the
plan exactly, and bracketing the HARQ budgets of 8 ms at 30 kHz and 16 ms at 15 kHz, which is
the day-5 prediction.

**Staleness floor:** measurement 6.44 ms old on arrival, action 6.44 ms late on landing, total
12.89 ms = **1.29x the fastest Near-RT loop period**. This is the NTN-specific result.

- [ ] Still open: gaseous attenuation magnitudes are placeholders, flagged at runtime, to be
      read off ITU-R P.676 before any figure containing them is published.

### Day 2 — array, beamforming, interference

**Done.** `make antenna`, `make antenna BAND=ka`.

- [x] 8x8 URA, TR 38.901 element pattern, steering vectors, array factor. Boresight 26.06 dBi,
      HPBW 12.56 deg, first sidelobe -14.04 dB, all measured off the sampled pattern
- [x] Hybrid 64 elements onto 4 RF chains, 6-bit analog phase, 4x4 digital
- [x] Interference from co-channel neighbours on the same ground track at the constellation's
      in-plane spacing, plus satellite-side beam discrimination
- [x] SINR(t) for fixed / ideal / quantised, exported to `data/array_{s,ka}.npz`
- [x] Figures 2 and 3

Results, and two of them contradict what the plan assumed:

- **6-bit quantisation costs 0.00 dB** of median SINR, not the "real and usually omitted" loss
  the plan asserted. It becomes real below three bits. Reported as found.
- **Open-loop pointing misses by more than a beamwidth near the horizon.** The element pattern
  pulls the composite lobe toward boresight: commanding 80 degrees lands the beam at 63.22, a
  16.78 deg error against a 12.56 deg beam. That is where handover happens, and it is a
  closed loop asking to be justified.
- **Beam dwell is 17.4 s at S-band** — a Non-RT-tier job. An 8x8 terminal would need
  141x141 elements before dwell fell to 1 s. Beam rate does not justify the Near-RT tier;
  the staleness floor and the handover decision do.
- **Bands must be compared at matched aperture, not matched element count.** At 52.5 cm both
  ways, S-band 8x8 gives 24.75 dB median SINR and Ka-band 98x98 gives 23.06 dB — near parity.
  What differs is dwell: 17.39 s against **1.43 s**, twelve times closer to the Near-RT ceiling.

- [ ] Beam squint across the pass, deferred: pointing error already dominates it by an order
      of magnitude, so it is not on the critical path to Figure 0.

### Day 3 — validation against a real satellite

- [ ] `satnogs/fetch.py`: pull passes from the SatNOGS archive by pinned observation ID
      (`satnogs/manifest.json`) together with the TLE that was current at capture time.
      Prefer narrowband CW/telemetry beacons in the 435 MHz band — they give the cleanest
      carrier to track.
- [ ] Optional and free: register with SatNOGS Network and **schedule an observation on a
      volunteer ground station**, then use your own resulting recording. This is the closest
      thing to operating a station that costs nothing, and it is worth a sentence in the paper.
- [ ] `satnogs/doppler_fit.py`: track the carrier (FFT peak, then a PLL or polynomial fit),
      produce measured Doppler against time, compare with the SGP4 prediction from day 1.
- [ ] Report **RMS error in Hz** and the residual's structure. A receiver clock offset shows as
      a constant; a stale TLE shows as a time shift; neither should be hidden.
- [ ] Artefact: Figure 3, measured against predicted Doppler.
- **Done when** the day-1 model is validated on data this lab did not generate. This figure is
  the credibility anchor of the whole repository.

### Day 4 — the link, and the shim that impairs it

- [ ] srsRAN Project gNB + Open5GS + srsUE over ZMQ inside `ntn-lab`. 10 MHz, logging low.
      This machine will not carry 100 MHz; do not try.
- [ ] `ranlink/shim/`: a ZeroMQ man-in-the-middle between gNB and UE applying, from the day-1
      time series — an NCO frequency shift, a **fractional-delay resampler**, and AWGN scaled
      by the day-2 SINR(t).
- [ ] Verify the shim in isolation first, against a synthetic tone, before it is anywhere near
      srsRAN. Debugging a resampler through a 5G stack is a bad day.
- **Done when** a UE attaches through the shim with impairments set to zero, and again with
  Doppler applied and delay still zero.

### Day 5 — where the link breaks

- [ ] Sweep one-way delay from 0 to 15 ms in steps, at SCS = 30 kHz and again at 15 kHz.
- [ ] Predictions to test, stated before the run: the RACH response window fails first; HARQ
      stalls beyond roughly 8 ms round trip at 30 kHz SCS (16 processes x 0.5 ms slots) but
      survives to roughly 16 ms at 15 kHz.
- [ ] Record the **exact srsRAN log line** at each failure. Quote it in the paper.
- [ ] Artefact: Figure 4 — attach success rate and throughput against one-way delay, annotated
      with the Rel-17 mechanism (K_offset, ephemeris-assisted common TA) that exists precisely
      to fix what is being observed.
- **Done when** there is a delay value with a failure mode and a log line attached to it.
  This is the most defensible result in the project: it is a measurement, not a claim.

### Day 6 — the microsecond tier in RTL

- [ ] `accel/rtl/`: CORDIC NCO plus complex mixer for Doppler pre-compensation; a 64-element
      phase-rotation datapath with a 6-bit phase LUT.
- [ ] cocotb + Verilator testbench driven by the **same** vectors as the day-1 and day-2 Python
      model. Report maximum error in LSB. Bit-exactness against a golden model is the claim
      that makes an unsynthesised core credible.
- [ ] One Vivado run targeting **xc7z020**: LUT, FF, DSP, BRAM, Fmax. State plainly in the
      README that this is synthesis only and no board was used. Do not imply otherwise.
- [ ] Vivado and srsRAN do not share a day. 7.9 GB.
- **Done when** the resource and timing table exists and the LSB error is reported.

### Day 7 — the microsecond tier on the GPU

- [ ] `accel/cuda/`: batched 4x4 Hermitian Cholesky solve for regularised-ZF / MMSE
      beamforming weights, hand-written, `nvcc -arch=sm_50`.
- [ ] Compare against cuSOLVER batched and against NumPy on the CPU. Time with Nsight.
- [ ] Sweep batch size. **Expect host-to-device transfer to dominate compute at this problem
      size.** That is a finding, not a failure: it says where the kernel belongs in the
      functional split, and it is a Figure 0 data point.
- **Done when** there is a batch size at which the GPU crosses over the CPU, and a stated
  consequence for RU-versus-DU placement.

---

## Week 2 — the control loops

### Day 8 — RIC and E2

- [ ] FlexRIC built in `ntn-lab`; srsRAN E2 agent connected; E2SM-KPM indications arriving.
- [ ] **Fallback, decided in advance rather than in a panic on day 11:** the mini-RIC from the
      first lab (`oran-lab/miniric/`) behind the same xApp interface. Whichever is used, the
      xApp code does not change.
- **Done when** KPM indications land in a store the day-9 xApp can read.

### Day 9 — the environment and the agent

- [ ] `xapp/env.py`: Gymnasium environment driven by the day-1 and day-2 outputs. Train
      offline; deploy against the live stack later.
- [ ] State: per-candidate RSRP/CQI/BLER, elevation, time to line-of-sight loss.
      Action: stay / switch beam / switch satellite / adjust A3 offset and time-to-trigger.
      Reward: throughput minus handover cost minus outage.
- [ ] **Partial observability is deliberate**: shadowing, blockage, measurement noise, and
      neighbour beams that are not fully observed. Without it the environment is deterministic
      and the correct criticism is "why not dynamic programming".
- [ ] PPO, small MLP, CPU.

### Day 10 — baselines, including the ceiling

- [ ] Baselines: max-RSRP, elevation-greedy, tuned hysteresis with time-to-trigger.
- [ ] **The DP oracle.** The orbit is deterministic, so the offline optimum is computable.
      Report the agent as a percentage of oracle. This is the difference between a result and
      a demo, and it also frames the comparison honestly: the oracle has perfect information,
      the agent does not.
- **Done when** the percentage-of-oracle number exists for both bands.

### Day 11 — close the loop for real

- [ ] Run the trained policy as an xApp against the live srsRAN stack over E2.
- [ ] Instrument the **indication to decision to control-ACK latency distribution**. This is the
      measured millisecond-tier point in Figure 0, and the number that decides whether the
      Near-RT tier can do this job at all.
- **Done when** the latency distribution is plotted next to the day-1 requirement for the same band.

### Day 12 — the rApp as a verified intent compiler

- [ ] Reuse the LangGraph and guardrail work from the first lab. The contribution is not that
      a model writes policy — that demo is saturated. The contribution is the verification:
      intent, then JSON A1 policy, then **JSON Schema validation plus a safety envelope**
      (power bounds, maximum handover rate, minimum elevation), then a reject-and-repair loop.
- [ ] `rapp/intents/`: 60 intents, written to include ambiguous, contradictory, out-of-bounds,
      and prompt-injection cases. The interesting numbers come from the hostile ones.
- [ ] Report schema validity rate, constraint violation rate, repair-loop convergence, and the
      effect on the xApp's realised reward. Report the failures.
- [ ] Measure end-to-end latency — the seconds-tier point in Figure 0.
- [ ] Qwen 2.5 3B on CPU. There is no GPU path on this machine.

### Day 13 — the runs and the figures

- [ ] Three arms, same seed: L1-only geometric steering / plus RL xApp / plus LLM policy shift
      mid-pass.
- [ ] CDFs of SINR, throughput, handover count, outage duration.
- [ ] **Figure 0.**

### Day 14 — ship it

- [ ] README with the architecture diagram and the result first, in the style of the first lab.
- [ ] Four-page IEEE workshop paper in `paper/`.
- [ ] `make all` reproduces every figure from clean. Time it and say how long it takes.
- [ ] CV bullets with the measured numbers substituted in. No placeholders left.

---

## The cut list

Decided now, not on day 12. If the schedule slips, drop in this order:

1. Intent benchmark 60 cases down to 25.
2. Hybrid analog/digital down to digital-only beamforming.
3. FlexRIC down to the mini-RIC fallback.
4. Vivado synthesis down to Verilator-verified RTL only, with the omission stated.

**Never cut:** the day-1 timescale derivation, the day-3 real-data validation, the day-5
delay breaking point, the day-10 oracle baseline. Those four are the scientific content. The
rest is engineering around them.

## Risks

| Risk | Mitigation |
|---|---|
| srsRAN will not run at all in 7.9 GB alongside the core | 10 MHz, logging off, no Vivado that day, mini-RIC instead of FlexRIC |
| FlexRIC build or version mismatch with the srsRAN E2 agent | fallback chosen on day 8, not day 11; identical xApp interface either way |
| SatNOGS has no clean beacon pass for the chosen satellite | pin several observation IDs in the manifest; 435 MHz CW beacons are plentiful |
| PPO does not beat tuned hysteresis | report it. The first lab's most interesting result was the model losing to a threshold controller |
| Vivado needs more RAM than the machine has for synthesis | small core, xc7z020, out-of-context synthesis only; if it still fails, cut-list item 4 |
| torch wheel has no sm_50 kernels | CPU-only torch by design; the CUDA work is hand-written and does not go through torch |
