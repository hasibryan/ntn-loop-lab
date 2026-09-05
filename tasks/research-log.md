# Research log

Dated, cited entries on what changed in the projects and literature this lab will be compared
with, and whether it changes the plan. Maintained by the `benchmark-researcher` agent
(`.claude/agents/benchmark-researcher.md`).

The operating principle is `tasks/lessons.md` 7.1: assumptions about what other people's
software does are hypotheses with a shelf life. An entry that says "no change" is a valid
entry — it records that the check was made and when.

Format, one per finding: date, source with a URL or a repository SHA, what it says in two
sentences, and what it changes here — a specific day in `tasks/todo.md`, a specific number, or
a specific claim in the README. "No change" is an acceptable answer to the last field.

---

## 2026-08-28 — srsRAN Project ships Rel-17 NTN mechanisms

**Source:** `configs/geo_ntn.yml` in `srsRAN_Project@release_25_10`, commit
`d2f4b70dda8e2c557d5b05a0ac5f92dbddda19bc` (2025-11-11).

`cell_specific_koffset`, `ta_common`, `ephemeris_info` and SIB19 scheduling are all present in
a config file shipped as a worked NTN scenario. The plan had assumed none of them existed and
had built the day-5 experiment around that absence.

**Changes:** day 5 in `tasks/todo.md`. The sweep no longer *points at* the Rel-17 mechanism
that would fix the failure — it switches it off and on across the same sweep, which turns a
gesture into a measurement. Written up in full at `tasks/lessons.md` 7.1. Note `geo_ntn.yml`
is a geostationary scenario, so its koffset of 150 is not the LEO value.
