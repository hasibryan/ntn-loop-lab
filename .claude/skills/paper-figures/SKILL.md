---
name: paper-figures
description: How figures and reported numbers are made in this lab — the measured-only rule, provenance from a run manifest, the Figure 0 timescale map, matplotlib house style, and what an axis must always carry. Use when producing any plot, table or number that will appear in the README, a figure or the paper.
---

# Figures and numbers

Figures here are evidence, not decoration. Each one answers a question that was written down
before the run that produced it.

## The measured-only rule

A number printed in a figure, a table, the README or the paper is one of exactly three things,
and which one is always visible to the reader:

1. **Measured** — produced by a run with a manifest in `data/logs/`. Default. No annotation
   needed beyond the caption naming the run.
2. **Derived** — computed analytically from measured or published inputs, such as the day-1
   required-loop-period table. Caption states the inputs and the assumption, for instance
   "residual CFO held under 2 % of SCS".
3. **Cited** — from a standard or a datasheet. Caption carries the reference.

An estimate that is none of the above does not go in a figure. If it must appear in prose,
the sentence says it is an estimate.

## Provenance

Every figure script reads from `data/`, never from a value pasted into the source. If a
number cannot be traced from figure to manifest to git commit, the figure is regenerated
rather than trusted. `make figures` must reproduce every image in `eval/figures/` from the
committed data with no manual step.

## Figure 0 — the timescale map

The one figure the project exists to produce. Log-log:

- **x**: required loop period, from `orbit/` on day 1, per band and subcarrier spacing.
- **y**: measured loop latency, from the RTL cycle count (day 6), the CUDA benchmark (day 7),
  the live E2 round trip (day 11) and the rApp end-to-end time (day 12).
- Shade the region where measured latency exceeds required period. A point in the shaded
  region is a tier that cannot do its assigned job.
- Mark S-band and Ka-band separately. They are the comparison, not two samples of one thing.

Every other figure is support for this one. If a plot does not feed it or explain it, ask
whether it belongs in the paper at all.

## House style

Follow the first lab's figures: readable at the width they are embedded, no chartjunk, no
gradient fills, no 3D bar charts. Concretely:

- Axes always carry units. Frequency in Hz, time in seconds or milliseconds with the prefix
  stated, angles in degrees, gain and SINR in dB with the reference named.
- Log axes are labelled as log axes and use decade ticks.
- Distributions are shown as CDFs, not as bar charts of means. The interesting part of an
  outage or a control-loop latency lives in the tail.
- Every comparison figure names the seed, the band and the SCS in the caption.
- Colour is not the only channel carrying meaning — arms are distinguishable in greyscale,
  because reviewers print things.
- Baselines are drawn, not described. If the claim is "better than max-RSRP", max-RSRP is a
  line on the same axes.

## Captions

A caption states what was measured, under what conditions, and what the reader should take
from it. Three sentences is usually right. A caption that only repeats the axis labels is
wasted; a figure that needs six sentences is two figures.

## Reporting a result that went against you

Say it plainly in the caption and keep the figure at full size. The first lab's most
valuable figure showed the language model losing to a threshold controller, and the
explanation of why was the part that made it worth reading. Shrinking or omitting an
unfavourable result is the one editorial decision that costs more credibility than the
result itself.
