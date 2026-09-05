# Lessons

Rules written for the next version of me, so the same mistake is not paid for twice. Carried
forward from the first lab, plus what the day-0 design pass corrected.

---

## 1. Physics that the plan got wrong before it was checked

### 1.1 A Doppler figure without a band is meaningless

The first draft of this project carried "±40 kHz" while naming both 2 GHz and 28 GHz. Those
differ by a factor of fourteen.

**Corrected on day 1 by the model itself.** The plan was drafted with ±48 kHz and 640 Hz/s,
taken from figures in common circulation. Both are wrong for this geometry, and the second
is wrong for an instructive reason. Computed values, 600 km circular orbit, overhead pass,
non-rotating Earth (`python -m orbit.pass_profile`):

| Band | Peak Doppler, to horizon | Peak Doppler, above a 10 deg mask | Peak Doppler rate |
|---|---|---|---|
| S, 2 GHz | 46.10 kHz | 45.40 kHz | 581.0 Hz/s |
| Ka, 28 GHz | 645.4 kHz | 635.7 kHz | 8134.7 Hz/s |

Two things the drafted numbers got wrong:

- Peak Doppler depends on the **horizon mask**. It is largest at the horizon, so quoting a
  peak without saying which elevation it was taken at is meaningless. This lab masks at
  10 degrees, and 45.4 kHz is the number that belongs in its figures.
- Doppler rate at closest approach is **not** `v^2 / (c h) * fc`. The satellite travels on an
  arc concentric with the station's radius vector, not on a straight-line flyby, so the
  effective transverse rate is `omega * sqrt(r * Re)` = 7.230 km/s rather than the orbital
  speed 7.562 km/s. The correct expression is `Re * r * omega^2 / h`, smaller by a factor
  `Re / r` = 0.914. That is 581 Hz/s, not 635 Hz/s.

**Rule:** every Doppler, delay or loss figure carries its band, its orbit altitude and its
horizon mask in the same sentence. And an anchor taken from memory is a hypothesis until the
model reproduces it — here the model won twice.

### 1.2 Delay is the problem, not Doppler

Doppler is pre-compensable open loop from ephemeris. Propagation delay is not compensable by
the terminal at all, and it is what breaks the protocol:

- 600 km, zenith: 2.0 ms one way, 4.0 ms round trip.
- 600 km, 10 degrees elevation: slant range about 1932 km, 6.4 ms one way, 12.9 ms round trip.
- NR HARQ with 16 processes at 30 kHz SCS covers 8 ms of round trip. At 15 kHz SCS, 16 ms.

**Rule:** when a plan for an NTN link talks about beamforming before it talks about timing,
the plan is optimising the wrong thing.

### 1.3 A control loop belongs to the timescale it can meet

Near-RT RIC is specified at 10 ms to 1 s. Slot-rate beam steering is L1. Proposing an RL xApp
that steers a beam per slot over E2 is not ambitious, it is architecturally impossible, and a
reader who works on O-RAN sees it immediately.

**Rule:** before assigning a function to a tier, compute the period the function needs and
compare it with the tier's specified budget. That comparison is the whole project.

### 1.3a Separate who computes a coefficient from who applies it

Day 1 produced a result that sharpens the thesis rather than confirming it. The Doppler
pre-compensation **coefficient** only needs recomputing every 516 ms at S-band and 37 ms at
Ka-band, to hold residual offset under 2 % of a 15 kHz subcarrier. Both of those sit inside
the Near-RT RIC's 10 ms to 1 s budget. Yet the coefficient must be **applied** to every
sample, at 245.76 Msample/s, which no RIC will ever do.

So the naive question "which tier owns Doppler pre-compensation" has no single answer, and
the interesting version is: the RIC can own the *policy* while the datapath owns the
*execution*. That split is what the day-6 RTL and the day-11 E2 latency measurement together
make concrete.

**Rule:** a tier assignment has two halves — computation rate and application rate. Conflating
them produces both of the errors this project was drafted with: putting beam steering in the
RIC because the decision is slow, and refusing to put anything in the RIC because the datapath
is fast.

### 1.3b The staleness floor is the NTN-specific failure

Also from day 1, and the number Figure 0 is really about. At a 10 degree elevation the
one-way delay is 6.44 ms. A measurement reaching the RIC is already 6.44 ms old; the resulting
action lands 6.44 ms late. Total irreducible staleness 12.89 ms, which is **1.29 times the
fastest Near-RT loop period** of 10 ms.

The Near-RT tier does not fail here because it is slow. It fails because it is looking at the
past and acting on the future, and no amount of xApp optimisation touches that. This is the
one part of the argument that is specific to non-terrestrial networks, and it is the sentence
the paper should be built around.

### 1.4 Interference needs a source before null-forming means anything

"Null-forming" with no defined interferer has no objective function. In this lab the
interferer is co-channel adjacent beams of the constellation, defined on day 2.

---

## 2. Claims that must be verified before they are written

### 2.1 Standards compliance

**Open, to close on day 0.** Does srsRAN Project implement any Rel-17 NTN feature — K_offset,
ephemeris-assisted common timing advance, cell-specific timing offset? Does OpenAirInterface?
The plan assumes srsRAN does not and turns that into the day-5 experiment. Record the answer
with a citation here before any README or paper text describes this testbed's standards
position.

**Rule:** never write "3GPP Release N compliant" about software whose feature list has not
been read. One overstated compliance claim discounts every honest number in the repository.

### 2.2 Hardware that was not used

There is no USRP and no FPGA board in this project, because a USRP is roughly a thousand
dollars and a PYNQ-Z2 is roughly two hundred. The RTL is verified in simulation and
synthesised out of context. The README says so once, plainly, and never softens it.

---

## 3. This machine

- GPU: GeForce 930MX, 2 GB, compute capability 5.0. vLLM needs 7.0 or above and will not run.
  TensorRT dropped Maxwell. CUDA 12.x is the last supporting line. Recent torch wheels ship no
  sm_50 kernels, so CUDA work here is hand-written with `nvcc -arch=sm_50` and torch stays on
  CPU.
- RAM: 7.9 GB. Vivado synthesis and the srsRAN stack do not share a day.
- The language model is Qwen 2.5 3B on CPU, shared with the first lab through a directory
  junction rather than copied.

**Rule:** check the hardware before designing around a library. The first draft of this
project specified vLLM, Llama-3-7B and TensorRT on a 2 GB Maxwell laptop GPU.

---

## 4. Process lessons carried from the first lab

### 4.1 Never `pkill -f` a broad pattern

`pkill -f 'python|xapp'` matches the invoking shell and kills it. Use the stop script, which
targets recorded PIDs.

### 4.2 A result that goes against the thesis is the most valuable thing in the repository

The first lab's headline was the language model losing to a threshold controller, with the
reason worked out and reported. That is what a reader remembers. Report the failure at full
size, explain the mechanism, and do not tune it away.

### 4.3 Check the harness before blaming the model

An earlier version of the first lab's comparison scored the agent far worse than it deserved
because of a flag in the test harness. When a result is surprisingly bad, the harness is a
more likely culprit than the algorithm.

### 4.4 Write the prediction before the run

Day 5's expected failure points are already recorded in `tasks/todo.md`. Comparing prediction
against measurement is the interesting part; writing the prediction afterwards destroys it.

---

## 5. Bugs days 1 and 2 paid for

### 5.1 A double conjugation steers the beam to minus the commanded angle

`conjugate_weights` returned `conj(a)/sqrt(N)` while `response_db` computed `a . conj(w)`.
The two conjugations cancel, so the main lobe landed at `-theta` instead of `+theta`.

It survived a first review because **boresight is degenerate**: at zero degrees the angle is
its own negative, so the pattern figure, the peak gain and the beamwidth were all correct.
The error only appeared once the beam was steered, as a 56 dB carrier collapse at 83 degrees
elevation, and it was found not by reading the code but by an assertion that a steered beam
cannot score worse than a beam pinned at zenith.

**Rule:** for anything with a pointing direction, test at a non-degenerate angle. A boresight
test proves nothing about steering, and boresight is exactly the case a person checks by eye.
`tests/test_antenna.py::test_array_factor_points_where_it_was_told` now sweeps seven angles.

### 5.2 An interference model with no discrimination term is not conservative, it is wrong

The first SINR model gave every co-channel neighbour full EIRP toward this terminal. That is
not a worst case, it is a different system: a multi-beam constellation points each beam at its
own cell, and an out-of-cell terminal sees the roll-off. The omission produced a median SINR
of -3 dB and, again, ranked an unsteered beam above a steered one.

The replacement is one parameter, `sat_beam_discrimination_db`, and because it is a scenario
value rather than a measurement the day-2 output **sweeps it** instead of quoting it. The
sweep is itself informative: between 10 and 40 dB of discrimination the median SINR moves by
0.35 dB while the 5th percentile moves by 10.8 dB. Interference only matters at the edges of
the pass, which is also where handover happens.

**Rule:** when a result rests on a parameter nobody measured, report the sensitivity, not the
point value.

### 5.3 Do not name a package after a standard-library module

`array/` shadowed Python's built-in `array` module and `python -m array.beams` failed with
`__path__ attribute not found`. Renamed to `antenna/`.

### 5.5 A missing term does not vanish; it reappears inside another one

Day 3 fitted the residual between this lab's Doppler prediction and a SatNOGS station's own
correction as `a0 + a1 * doppler + a2 * doppler_rate` — a constant, a scale error and a time
shift. On KKS-1 it returned **a1 = +5129 ppm**: half a percent of disagreement between two SGP4
implementations propagating the same TLE. That would have been a real finding if it were true.

It was not there. The beacon's oscillator was drifting as it warmed through the pass, at
-0.35 Hz/s, and the model had no term for a drift. Over a single pass the Doppler curve is close
enough to linear in time that the scale term could absorb it, so it did. Fitting a plain linear
drift *instead* explained the same residual better — 6.7 Hz unexplained against 13.3 Hz — and
with both terms present the scale collapsed to -680 ppm.

The dangerous part is not the error. It is that +5129 ppm is small enough to look like a
plausible model discrepancy rather than an artefact, so it would have been written down.

The two terms remain correlated at -0.96 over one pass, so the fit now reports the split as
**not separable** rather than reporting a number for it. That is 5.2's rule again: where a
result rests on a distinction the data cannot make, say it cannot be made.

**Rule:** before believing a fitted coefficient, fit the competing explanation on its own and
see which one wins, then fit both and see whether the first survives. A term that has nowhere
to go goes somewhere.

### 5.6 If the answer moves with the knob, it is a fact about the knob

Two of the four day-3 captures came from a station whose recordings carry a second strong
signal. Selecting the beacon needs a frequency window around it, and for those two the residual
RMS scaled linearly with the window width: 26 Hz at +/-150 Hz, 124 Hz at +/-400 Hz. Any single
number quoted would have described the window.

There was a tempting number available — the narrow window gives 26 Hz, which is *better* than
the two good captures and would have made day 3 look stronger. Reported as **not measurable**
instead, with the mechanism, and the window-ratio test is now automatic: a capture is rejected
unless RMS at the wide and narrow windows agrees within 50 %.

**Rule:** every selection parameter gets swept before its result is quoted. If the result moves
with it, there is no result -- and the direction it moves is not a reason to pick a value.

---

## 6. What days 1 and 2 actually found

Measured, and each one reproducible from `make orbit` and `make antenna`.

### 6.1 Open-loop pointing misses by more than a beam near the horizon

The element pattern falls while the array factor rises, so the composite lobe lands short of
the commanded angle. For the 8x8 array, boresight HPBW 12.56 degrees:

| commanded | lands at | error |
|---|---|---|
| 15 deg | 14.35 | 0.65 |
| 45 deg | 41.85 | 3.15 |
| 60 deg | 53.50 | 6.50 |
| 80 deg | 63.22 | **16.78** |

At 80 degrees off boresight — a satellite at 10 degrees elevation, which is exactly where
acquisition, release and handover happen — a terminal steering open loop from ephemeris misses
by more than a full beamwidth. That is a systematic bias, not noise, and it is a closed loop
waiting to be justified.

### 6.2 Six-bit phase quantisation is free; the interesting cost is elsewhere

A 6-bit shifter in a 64-element, 4-chain hybrid costs **0.00 dB** of median SINR and 0.01 dB
of peak gain. The plan asserted this would be "real and usually omitted". It is not, at six
bits. It becomes real below about three, which is what the test exercises. Reported as found.

### 6.3 Beam tracking does not need a fast loop, and that is the finding

Peak line-of-sight rate for a 600 km overhead pass is 0.722 deg/s. With a 12.56 degree beam
the satellite stays inside it for **17.4 s**. Beam tracking at S-band is a Non-RT-tier job,
not a Near-RT one, and an 8x8 terminal would need to grow to **141x141 elements** before dwell
fell to one second.

The Near-RT tier is therefore not justified by beam rate. What justifies it is the staleness
floor of 1.3.b and the handover decision, which is a much sharper claim than the one the plan
started with.

### 6.4 Comparing bands at equal element count is comparing two different antennas

An 8x8 array at 0.5 wavelength spacing is 52.5 cm across at S-band and 4.3 cm at Ka. Compared
that way Ka looks 23 dB worse, which is just the path-loss ratio 20 log10(14) reappearing as
an antenna the physics never asked for.

At **matched physical aperture** — 52.5 cm, so 98x98 = 9604 elements at Ka — the two bands
come out at 24.75 dB and 23.06 dB median SINR. Near parity. What actually differs between them
is not the link budget:

| | S-band, 8x8 | Ka-band, 98x98, same 52.5 cm |
|---|---|---|
| peak gain | 26.06 dBi | 47.82 dBi |
| HPBW | 12.56 deg | 1.03 deg |
| median SINR | 24.75 dB | 23.06 dB |
| beam dwell | 17.39 s | **1.43 s** |
| Doppler rate | 581 Hz/s | 8135 Hz/s |

Ka's beam dwell of 1.43 s sits just outside the Near-RT budget's 1 s ceiling, twelve times
closer to it than S-band. It is the **band and aperture together**, not the band, that decide
which tier owns beam tracking.

**Rule:** when comparing two frequencies, say what is being held constant. Element count and
physical aperture give opposite answers, and only one of them corresponds to a terminal
somebody could build.

### 5.4 A pattern evaluation is an n_angles x n_elements allocation

`response_db` built the whole phase array in one go. For the aperture-matched Ka array that
is 4001 angles x 9604 elements of complex128 — **615 MB in a single allocation**, on a machine
with 7.9 GB of RAM and a 5G stack expected to share it. The symptom was not an error, it was a
day-2 run that took over four minutes and pushed the machine into swap.

Fixed by evaluating in chunks bounded at roughly 64 MB, and by splitting `sinr_over_pass` into
an expensive gain pass and a cheap budget pass so the discrimination sweep reuses gains instead
of recomputing them five times. S-band run: 4.8 s. Ka at 9604 elements: 69 s.

**Rule:** when array size is a parameter, check what the largest configuration allocates before
running it. On this machine the difference between "vectorised" and "chunked" is the difference
between fast and swapping.

---

## 7. Answered from outside this repository

### 7.1 srsRAN Project does implement Rel-17 NTN, and the day-5 experiment is better for it

Day 0 left an open question, and the plan wrote its assumption into the schedule: *does srsRAN
Project implement any Rel-17 NTN feature — `K_offset`, ephemeris-assisted common TA, cell-specific
timing offset? The plan assumes srsRAN does not, and treats that as the experiment rather than a
defect.*

**The assumption is wrong.** Read on 2026-08-28 off `configs/geo_ntn.yml` in
`srsRAN_Project@release_25_10` (commit `d2f4b70dda8e2c557d5b05a0ac5f92dbddda19bc`, 2025-11-11),
cloned while setting up the neighbouring `oran-kpm-guard` project:

```yaml
ntn:
  cell_specific_koffset: 150   # sets the maximum possible channel delay
  ta_common: 0
  ephemeris_info:              # ecef ephemeris information for the satellite
  sib:                         # system information block 19 scheduling, SIB19 is the NTN information block
```

All three mechanisms the plan named are present, plus SIB19 scheduling, in a config file shipped
as a worked NTN scenario.

This makes the day-5 experiment stronger rather than redundant. The plan was going to sweep
one-way delay until RACH and HARQ broke, then *point at* the Release 17 mechanism that exists to
fix it. The mechanism can instead be **switched off and on across the same sweep**, which turns a
gestured-at fix into a measured one: the same failure, the same log line, and then the delay at
which it no longer occurs with `cell_specific_koffset` configured.

Two things this does not change. The README's claim that this is *not* a Rel-17 NTN compliant
testbed still stands until compliance is demonstrated rather than assumed from a config key. And
`geo_ntn.yml` is named for a geostationary scenario, so its `koffset` of 150 is not the LEO value
— the day-1 delay derivation supplies that.

**Rule, and it is the same one as 1.1 in a different costume:** the plan's assumptions about what
other people's software does are hypotheses with a shelf life, and they are cheapest to check on
the day the repository is first cloned. This one was free — it fell out of a clone made for
another project — and it would have cost a day of building an experiment around an absence that
was not there.

---

## 8. What day 3 found

### 8.1 The archive had already solved the problem the plan came to measure

Day 3 was planned as: track the raw carrier in a recorded pass, compare against SGP4, report
RMS error in Hz. The plan assumed the archived audio carries the raw carrier.

It does not. Measured on all four captures before anything was fitted, the carrier sits between
roughly 300 Hz and 3 kHz of audio and never sweeps, where an uncorrected 437 MHz LEO carrier
would sweep about +/-10 kHz and 48 kHz audio has ample room to show it. SatNOGS stations apply
Doppler correction at the receiver before archiving.

That makes day 3 a *stricter* test than the one planned, not a weaker one. Both sides propagate
the same TLE — the one the station held at capture, saved alongside the audio — with SGP4, so a
correct model predicts a flat residual and every Hz of structure in it is real disagreement
between two independent implementations.

**Measured, on the two captures where the measurement is well posed:** residual RMS 14.4 Hz
(SEEDS, 76.7 deg peak) and 39.1 Hz (KKS-1, 76.4 deg peak). The larger of those is **0.39 % of
the 9.9 kHz Doppler the station removed**, falling to 6.5 Hz — 0.066 % — once the beacon's own
oscillator drift is accounted for.

**Rule, and it is 7.1 wearing different clothes:** check what the data has already had done to
it before designing a measurement around what you assume it is. The check cost one FFT.
