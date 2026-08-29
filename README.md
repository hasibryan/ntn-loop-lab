# NTN loop lab — where does the control loop live when the cell moves at 7.5 km/s?

An O-RAN non-terrestrial network testbed built to answer one question, on one laptop, offline.

A LEO satellite pass demands three control loops at wildly different rates: Doppler
pre-compensation in microseconds, beam and satellite selection in milliseconds, mission
policy in seconds. O-RAN already has three places to put them — L1, the Near-RT RIC, the
Non-RT RIC. **This lab measures whether that assignment survives a cell moving at 7.5 km/s.**

Not a survey, not a demo reel. One question, measured end to end, with the failures reported.

---

## Status

**Day 2 of 14.** The physics and the antenna are done and tested; the link, the silicon and
the control loops are not. 29 tests pass. Everything below is reproducible with `make orbit`
and `make antenna`.

### The first result, and it is not the one the plan expected

A Near-RT RIC control loop over a 600 km LEO link has an **irreducible staleness of 12.89 ms**
at 10 degrees elevation — the measurement is 6.44 ms old when it arrives, the action is
6.44 ms late when it lands. That is **1.29 times the fastest Near-RT loop period** the
specification allows. The tier does not fail because it is slow; it fails because it is
looking at the past and acting on the future, and no xApp optimisation touches that.

Meanwhile the job the plan wanted to give that tier does not need it. Beam tracking at S-band
has a **17.4 s** dwell — the satellite crosses a 12.56 degree beam that slowly. An 8x8
terminal would need to grow to **141x141 elements** before dwell fell to one second.

| | S-band, 8x8 | Ka-band, 98x98, same 52.5 cm aperture |
|---|---|---|
| peak Doppler (10 deg mask) | 45.40 kHz | 635.65 kHz |
| peak Doppler rate | 581.0 Hz/s | 8134.7 Hz/s |
| CFO update period, 15 kHz SCS | 516 ms | 36.9 ms |
| boresight gain / HPBW | 26.06 dBi / 12.56 deg | 47.82 dBi / 1.03 deg |
| median SINR over a pass | 24.75 dB | 23.06 dB |
| beam dwell | 17.39 s | **1.43 s** |

Compared at equal element count Ka looks 23 dB worse, which is just the path-loss ratio
reappearing as an antenna nobody would build. At equal *physical aperture* the two bands are
at parity on SINR and differ by twelve times on dwell. It is band and aperture together, not
band, that decide which tier owns beam tracking.

### And two things the plan asserted that turned out to be false

- **6-bit phase quantisation costs 0.00 dB** of median SINR in a 64-element, 4-chain hybrid,
  not the "real and usually omitted" penalty the plan claimed. It matters below three bits.
- **Open-loop pointing misses by more than a beamwidth near the horizon.** The element pattern
  pulls the composite lobe inward: command 80 degrees off boresight and the beam lands at
  63.22, a 16.78 degree error against a 12.56 degree beam — at exactly the elevation where
  acquisition, release and handover happen.

The plan's own Doppler anchors were also wrong, and the model corrected them before anything
was built on top: 45.4 kHz and 581 Hz/s at S-band, not 48 kHz and 640 Hz/s. Both corrections,
and the two beamformer bugs found on the way, are written up in
[tasks/lessons.md](tasks/lessons.md).

The plan, its acceptance criteria, its cut list and its risk register are in
[tasks/todo.md](tasks/todo.md).

---

## The headline figure this exists to produce

**Figure 0, the timescale map.** Required loop period, derived from orbital dynamics, against
loop latency measured on this stack — the RTL cycle count, the CUDA kernel, the live E2 round
trip, the rApp end to end. Log-log, with the infeasible region shaded.

The hypothesis, to be confirmed or refuted: at S-band the Near-RT RIC tier fits comfortably;
at Ka-band the Doppler rate is roughly fourteen times higher and it does not. If that holds,
it is a measured statement about where O-RAN's functional split has to change for NTN.

---

## What gets built

| Tier | Required period | Implementation | Directory |
|---|---|---|---|
| Physics | — | SGP4 pass profile, TR 38.811 channel, required-loop-period derivation | [orbit/](orbit/) |
| Antenna | — | 8x8 URA, hybrid 64x4, 6-bit quantised phase, adjacent-beam interference | [antenna/](antenna/) |
| Validation | — | real LEO passes from the SatNOGS archive, carrier tracked, fitted against SGP4 | [satnogs/](satnogs/) |
| Link | — | srsRAN Project + Open5GS over ZMQ, through a Doppler and fractional-delay shim | [ranlink/](ranlink/) |
| L1, microseconds | set by CFO tolerance | CORDIC NCO and beamformer in RTL; batched Cholesky MMSE in CUDA | [accel/](accel/) |
| Near-RT, milliseconds | set by link-margin collapse | PPO xApp for beam and satellite selection over E2 | [xapp/](xapp/) |
| Non-RT, seconds | set by mission cadence | LLM intent compiler emitting schema-validated A1 policy | [rapp/](rapp/) |

---

## What is honest about this repository

Stated once, plainly, and not softened later:

- **No radio hardware was purchased.** The real-capture work uses recordings from the SatNOGS
  volunteer ground-station network. Where an observation was scheduled on someone else's
  station, that is said.
- **No FPGA board was used.** The RTL is verified bit-exact against the Python golden model in
  Verilator, and synthesised out of context for an xc7z020. Resources and Fmax come from
  synthesis, not from implementation or from silicon.
- **This is not a Rel-17 NTN compliant testbed.** srsRAN's NTN feature status is recorded in
  [tasks/lessons.md](tasks/lessons.md) with a citation. The gap is the day-5 experiment: sweep
  the propagation delay until RACH and HARQ break, record the exact failure, and point at the
  Release 17 mechanism that exists to fix it.
- **Every number here is measured, derived or cited**, and which one it is is always visible.

---

## Running it

```bash
wsl -d ntn-lab
cd /mnt/d/ntn-loop-lab
make doctor          # toolchain, distro, GPU, Ollama, disk
make help            # every stage of the plan, one target each
```

The lab lives inside a WSL2 distro cloned from the first lab's, stored in `wsl/` and ignored
by git. The Ollama binary and the Qwen 2.5 3B weights are shared with the first lab through a
directory junction rather than duplicated. Nothing installs outside this folder.

## Related work by the same author

[O-RAN Mini-Lab](../LLM_Learning) — a five-cell LTE network, an E2 interface, and a 3B
language-model agent that fixes congestion, together with the sixteen-lesson curriculum that
builds it. Its mini-RIC is this project's documented fallback if FlexRIC does not cooperate.
