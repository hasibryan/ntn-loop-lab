---
name: ntn-run
description: Run, compare and record NTN loop-lab experiments without invalidating the results — band and SCS pinning, arm definitions, seed discipline, and the rule that every reported number is measured. Use whenever starting a run, reproducing a figure, or comparing control arms.
---

# Running an experiment in the NTN loop lab

The mistake this skill exists to prevent is not a crash. It is producing numbers that look
fine and mean nothing — a comparison across two different bands, an agent arm that quietly
ran with a different seed, or an estimate that gets written into the paper as a measurement.

## Before anything else

```bash
wsl -d ntn-lab -- bash -c "ss -ltn | grep -E ':(2000|2001|36421|36422|38412) '"
```

Anything bound means a previous run is still alive: the ZMQ ports the shim sits between,
the E2 ports, or the NGAP port to Open5GS. Clear it with:

```bash
wsl -d ntn-lab -- bash /mnt/d/ntn-loop-lab/scripts/stop_lab.sh
```

Never `pkill -f` a broad pattern such as `python|xapp|srs`. It matches the invoking shell
and kills it. That lesson was paid for once already in the first lab.

## Every run is pinned on three axes

A result is only comparable to another result if all three match.

| Axis | Values | Where it comes from |
|---|---|---|
| `BAND` | `s` (2 GHz) or `ka` (28 GHz) | selects the day-1 channel file; changes Doppler by 14x |
| `SCS` | `15` or `30` kHz | changes the HARQ round-trip budget and the CFO tolerance |
| `SEED` | integer | the environment's noise, blockage and arrival process |

`BAND` is the one that gets forgotten. S-band and Ka-band results are not two points on the
same curve unless the figure says which is which, because the required loop period differs
by more than an order of magnitude.

## The arms

| Arm | What runs | What it is for |
|---|---|---|
| `l1` | geometric steering plus open-loop Doppler pre-compensation from ephemeris | the control arm; everything else must beat it |
| `rl` | plus the PPO xApp doing beam and satellite selection over E2 | the Near-RT tier under test |
| `rl+intent` | plus the LLM rApp shifting A1 policy mid-pass | the Non-RT tier under test |
| `oracle` | offline dynamic programme with perfect information | the ceiling; not a competitor, a denominator |

`oracle` is not optional. An RL number without it is a demo. Report the agent as a
percentage of oracle, and state in the same sentence that the oracle sees what the agent
cannot.

## One run

```bash
wsl -d ntn-lab -- env BAND=s SCS=30 SEED=1 bash /mnt/d/ntn-loop-lab/scripts/run_experiment.sh rl
```

Logs land in `data/logs/`. Every run writes a manifest recording the git commit, the three
axis values, the TLE epoch, and the wall-clock duration. If a figure cannot be traced back
to a manifest, the figure does not go in the paper.

## The rules that make the numbers mean something

1. **Every number is measured.** If a value is an estimate, a datasheet figure or a
   back-of-envelope calculation, it is labelled as one, in the figure and in the text.
2. **A negative result is reported.** The first lab's best result was the language model
   losing to a threshold controller, explained rather than tuned away. The same standard
   applies here: if PPO does not beat tuned hysteresis, that is the finding.
3. **Predictions are written before the run, not after.** Day 5's expected failure points are
   already in `tasks/todo.md`. Comparing the prediction with the measurement is the
   interesting part; retrofitting the prediction destroys it.
4. **Latency claims come from instrumentation, not from a specification.** The Near-RT RIC is
   specified at 10 ms to 1 s. What matters for Figure 0 is what this stack actually does,
   measured on day 11.
5. **Standards claims get checked before they are written.** In particular, do not describe
   anything in this repository as Rel-17 NTN compliant without a citation to the feature in
   the implementation. The absence of those features is the experiment, not an embarrassment.
