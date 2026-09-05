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
