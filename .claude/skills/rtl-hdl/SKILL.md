---
name: rtl-hdl
description: Conventions for the RTL and CUDA work in accel/ — golden-model bit-exactness, the cocotb and Verilator workflow, fixed-point discipline, what may and may not be claimed about an unsynthesised or board-less core, and the memory budget that keeps Vivado and srsRAN off the same day. Use when writing, testing or reporting hardware kernels.
---

# Hardware kernels in this lab

Two kernels exist, both serving the microsecond tier of the timescale map:

- `accel/rtl/` — a CORDIC NCO and complex mixer for Doppler pre-compensation, plus a
  64-element phase-rotation beamformer with a 6-bit phase lookup.
- `accel/cuda/` — a batched 4x4 Hermitian Cholesky solve producing regularised-ZF and MMSE
  beamforming weights for the four digital chains of the hybrid array.

Neither is interesting on its own. Both exist to produce one number each for Figure 0: how
long the microsecond tier actually takes.

## The golden model rule

No hardware in this repository is verified against hand-written expected values. Every
testbench is driven by the **same** vectors the Python model in `orbit/` and `antenna/`
produced, and the pass criterion is bit-exactness or a stated maximum error in LSB.

```
orbit/pass_profile.py  ->  data/golden/nco_vectors.npz  ->  cocotb testbench
antenna/beams.py         ->  data/golden/weights.npz      ->  cocotb testbench + CUDA test
```

If the RTL and the model disagree, the default assumption is that the RTL's fixed-point
format is wrong, not that the model is. Record the resolved discrepancy in
`tasks/lessons.md`; quantisation surprises are the most reusable lessons in this directory.

## Fixed point

Declare the format in a comment at the top of every module — total width, integer bits,
signedness, and where rounding happens. `Q1.15` written down beats `Q1.15` inferred from a
shift. The phase accumulator width sets the NCO's frequency resolution; state the resulting
Hz-per-LSB next to the declaration, because that number is what the day-1 CFO tolerance is
compared against.

## The simulation loop

```bash
make -C accel/rtl sim          # cocotb driving Verilator; seconds, run it constantly
make -C accel/rtl synth        # Vivado, xc7z020, out-of-context; minutes, run it rarely
```

Verilator is the working loop. Vivado runs once per meaningful change, for numbers only:
LUT, FF, DSP, BRAM, Fmax.

**Vivado and srsRAN never run on the same day.** This machine has 7.9 GB of RAM. Synthesis
of a small core and a 5G stack with a core network will not both fit, and the failure mode
is a swap-thrashed machine rather than a clean error.

## What may be claimed

There is no board. The honest claim set is:

- Verified bit-exact against a golden model in simulation — say which simulator.
- Synthesised out of context for xc7z020 — give resources and Fmax, and say it is synthesis,
  not implementation, unless place-and-route was actually run.
- Latency in cycles at a stated clock, converted to microseconds.

What may not be claimed: throughput measured on hardware, power figures, or timing closure
in a full design. Write "synthesis only, no board" in the README once and do not soften it
later. A reader who finds one overstated hardware claim discounts every other number in the
repository, including the ones that are solid.

## The CUDA side

The GPU is a GeForce 930MX: compute capability 5.0, 2 GB, 384 cores. Consequences that are
not optional:

- Compile with `nvcc -arch=sm_50`. CUDA 12.x is the last line that supports Maxwell.
- Do not route this through torch. Recent wheels ship no sm_50 kernels; the CPU-only torch
  in `requirements.txt` is there for stable-baselines3 and nothing else.
- TensorRT does not support this device. Do not plan around it.

Benchmark against two references, not one: cuSOLVER batched, and NumPy on the CPU. Sweep the
batch size and report the crossover. At a 4x4 problem size, host-to-device transfer is
expected to dominate compute — that is a result about where the kernel belongs in the O-RAN
functional split, and it belongs in the paper rather than being engineered away.
