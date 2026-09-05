# Mistakes

The live register. Every defect found in this repository gets a dated row here, whether it was
found by review, by a test, or by the number turning out wrong.

This file is **not** a replacement for [tasks/lessons.md](tasks/lessons.md). The two have
different jobs:

- **`Mistakes.md`** is the working queue — one row per finding, with a status. Rows are never
  deleted, only re-statused.
- **`tasks/lessons.md`** is the distilled artefact — a rule written for the next version of us,
  with the mechanism explained, for the findings general enough to earn one.

A finding graduates from here to there when it is fixed *and* the rule generalises. The row
then reads `promoted` and cites the lessons.md section.

Owned by the `critique-agent` (`.claude/agents/critique-agent.md`), but anyone may add a row.

| status | meaning |
|---|---|
| `open` | found, not yet fixed |
| `fixed` | corrected; the rule is too specific to promote |
| `promoted` | corrected, and the durable rule is now in `tasks/lessons.md` |
| `wontfix` | a real limitation, accepted deliberately, reason recorded |

---

## Register

| # | Date | Where | Finding | Status |
|---|---|---|---|---|
| 1 | 2026-08-28 | `orbit/channel.py::gaseous_loss_db` | Gaseous attenuation magnitudes are placeholders, flagged at runtime. They must be read off ITU-R P.676 before any published figure contains them. No figure currently does, which is why this is open rather than urgent. | `open` |
| 2 | 2026-08-28 | `antenna/` | Beam squint across the pass is not modelled. Deferred deliberately: open-loop pointing error already dominates it by an order of magnitude (lessons.md 6.1), so it is not on the critical path to Figure 0. Revisit if a result starts depending on wideband behaviour. | `wontfix` |
| 3 | 2026-09-05 | `satnogs/doppler_fit.py::track_carrier` | First day-3 run reported a residual RMS of 262 to 502 Hz and it was briefly read as a model error. It was the tracker: a 10 dB SNR gate let noise-bin picks through, and on two captures a second strong signal in the band was being tracked instead of the beacon. Fixed by raising the gate to 15 dB and adding `select_carrier`, whose discriminator is physical — the station corrected Doppler for this satellite and nothing else, so the beacon is the only line stationary in frequency. RMS fell to 14.4 and 39.1 Hz. | `promoted` (lessons.md 4.3, already stated; this is its second bill) |
| 4 | 2026-09-05 | `satnogs/doppler_fit.py::decompose_residual` | The three-term fit had no linear-in-time term, so a beacon oscillator warming through the pass came back as a **+5129 ppm Doppler-scale error** on KKS-1 — half a percent of disagreement between two SGP4 implementations on the same TLE, which would have been a serious and wrong claim, and it would have been believed because it was small enough to look plausible. Caught by fitting a plain linear drift instead and finding it explained the same residual better (6.7 Hz unexplained against 13.3 Hz). Fixed by fitting both; the scale then collapses to -680 ppm. | `promoted` (lessons.md 5.5) |
| 5 | 2026-09-05 | `satnogs/captures/14911409`, `14911418` | Both `berlin_ma_sat` captures carry a second signal this tracker cannot separate. Their residual RMS scales linearly with the carrier-selection window (26 Hz at +/-150 Hz, 124 Hz at +/-400 Hz), so any number quoted would be a fact about the window. Reported as rejected, with the window-ratio test now automatic in `doppler_fit`. A tracker that follows a sweeping interferer as a second track would recover them. | `wontfix` |

---

## Findings already promoted

These were found and fixed before this register existed. They live in `tasks/lessons.md` in
full and are listed here so the history is complete.

| Date | Finding | Lesson |
|---|---|---|
| 2026-08-26 | Double conjugation steered the beam to `-theta`; survived review because boresight is degenerate. | 5.1 |
| 2026-08-26 | Interference model gave every neighbour full EIRP — not conservative, a different system. | 5.2 |
| 2026-08-25 | `array/` shadowed Python's stdlib `array` module. | 5.3 |
| 2026-08-26 | `response_db` allocated 615 MB in one go for the aperture-matched Ka array. | 5.4 |
| 2026-08-25 | The plan's Doppler anchors (48 kHz, 640 Hz/s) were wrong; the model corrected them to 45.40 kHz and 581.0 Hz/s. | 1.1 |
| 2026-08-28 | The plan assumed srsRAN Project implements no Rel-17 NTN feature. It implements all three named, plus SIB19 scheduling. | 7.1 |
