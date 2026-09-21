# Tickets

Working queue derived from `tasks/todo.md`. That file stays the spec (what each day means,
predictions, acceptance criteria); this file is status only. Update status here as work lands;
edit the write-up in `todo.md`/`README.md`/`lessons.md` as usual.

Status: OPEN (ready to pull) · BLOCKED (named dependency) · DEFERRED (decided cut, not a bug) · DONE

| ID | Day | Title | Status | Blocked by | Ref |
|---|---|---|---|---|---|
| T00 | 0 | Reconcile stale checkboxes (`git init`/first commit, `make doctor`, srsRAN Rel-17 verify) | DONE | — | todo.md:57-66, lessons.md 7.1 |
| T15 | 7 | Install CUDA toolkit in `ntn-lab` — `nvcc` absent, blocks the day-7 kernel | OPEN | — | found by T00, todo.md:59-62 |
| T16 | 12 | Register the junctioned GGUF weights with Ollama — `ollama serve` answers but `/api/tags` lists zero models | OPEN | — | found by T00, todo.md:59-62 |
| T01 | 1 | Replace placeholder gaseous attenuation with real ITU-R P.676 values | DONE | — | todo.md:97-98, Mistakes.md #1 |
| T02 | 2 | Beam squint across the pass | DEFERRED | — | todo.md:127-128 (pointing error already dominates by an order of magnitude) |
| T03 | 3 | Schedule a self-observation on SatNOGS Network, use own recording | OPEN | — | todo.md:136-137 (optional, free) |
| T04 | 3 | Validation capture from a station that does NOT Doppler-correct before archiving | OPEN | — | lessons.md 5.7, README "still open" |
| T05 | 4 | srsRAN Project gNB + Open5GS + srsUE over ZMQ inside `ntn-lab`, 10 MHz | OPEN | — | todo.md:245-246 |
| T06 | 4 | `ranlink/shim/`: NCO shift + fractional-delay resampler + AWGN; verify standalone against a synthetic tone first | OPEN | — | todo.md:247-251 |
| T07 | 5 | Delay-breaking sweep, 0-15 ms, SCS 15/30 kHz; predictions written first; repeat with `cell_specific_koffset` on/off (Rel-17 mechanism confirmed present, lessons.md 7.1) | BLOCKED | T05, T06 | todo.md:255-266 |
| T08 | 6 | RTL: CORDIC NCO + 64-element phase-rotation datapath; cocotb/Verilator bit-exact vs golden model; Vivado xc7z020 synthesis-only | OPEN | — | todo.md:268-278 |
| T09 | 7 | CUDA batched 4x4 Cholesky MMSE kernel, `sm_50`, vs cuSOLVER/NumPy, Nsight timing | OPEN | — | todo.md:280-289 |
| T10 | 8 | RIC/E2 bring-up (FlexRIC or mini-RIC fallback) | BLOCKED | `oran-kpm-guard` (real E2 interface) | README "Days 8 to 11 remain deliberately blocked" |
| T11 | 9 | RL xApp Gymnasium env + PPO (offline training) | BLOCKED | oran-kpm-guard | README, todo.md:303-313 |
| T12 | 12 | rApp intent compiler (LangGraph + guardrails + schema validation), 60-intent benchmark | OPEN — not on the README's blocked list, independent of live E2 | — | todo.md:332-343 |
| T13 | 13 | Three-arm runs + Figure 0 | BLOCKED | T07, T10, T11, T12 | todo.md:345-350 |
| T14 | 14 | Ship: README diagram, paper, `make all`, CV bullets | BLOCKED | T13 | todo.md:352-357 |

## Pull order right now

Unblocked and independent of each other — pick any: **T03, T04, T08, T09, T12, T15, T16.**
T05 → T06 → T07 is the critical link-and-silicon chain and the main line of "the next work" per
README. T10/T11/T13/T14 stay parked until `oran-kpm-guard`'s E2 interface lands.
