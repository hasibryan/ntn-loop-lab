# `oran-kpm-guard` — build plan

**Written 2026-08-26.** Hand this whole file to a fresh Claude Code session on the Ubuntu
machine as the opening prompt. It is written for a coding agent, not for reading.

---

## 0. Read this before running anything

**Three rules that govern the whole build. They override any instinct to make progress look faster.**

1. **Never claim a phase done without the end artifact.** Exit code 0 is not evidence.
   "docker compose up succeeded" is not evidence. The evidence is the *KPM measurement value
   printed by the xApp*, the *CSV row on disk*, the *plot*. Each phase below names its artifact.
   If you cannot produce it, write `UNVERIFIED` in the log and stop.
2. **Do not invent commands, flags, config keys or file paths.** Everything in §2 marked
   `[VERIFIED]` was read off the upstream docs on 2026-08-26. Everything marked `[DISCOVER]`
   is unknown and must be found by reading the actual repo you just cloned — `ls`, `--help`,
   the README in the clone, the config samples in the tree. If you guess a flag and it silently
   does nothing, the whole dataset is garbage and nobody finds out for a week.
3. **Log every environment deviation** in `NOTES.md` as you go — version mismatches, packages
   you had to install, files whose paths differ from this plan. That file is the honest half of
   reproducibility and it is also what makes the README credible later.

---

## 1. What this project is, and why it is worth the days

An **xApp that detects cell degradation from live E2SM-KPM telemetry on a real O-RAN stack**,
plus a **released labelled dataset of KPM traces under injected faults**.

### Why not another simulator

There is an existing repo (`LLM-Learning`, being renamed to `oran-mini-lab`) with a **self-built**
Near-RT RIC: real 3GPP measurement names and service-model OIDs, but newline-delimited JSON over
TCP instead of ASN.1 APER over SCTP, and ns-3 instead of a gNB. It is good learning and a fine
teaching artifact. It is weak as a credential, because the first question any O-RAN supervisor
asks is "did you touch a real E2 interface", and the answer is currently no.

This project answers yes. Same person, same skills, real stack:

| | old lab | this |
|---|---|---|
| RIC | self-built | OSC Near-RT RIC (`i-release`) |
| E2 wire | JSON/TCP | real E2AP |
| RAN | ns-3 / analytic | srsRAN Project gNB |
| Core | none | Open5GS |
| Radio | none | ZMQ emulation (**no SDR needed**) |

### Why *this* use case

Sleeping cells, PRB starvation and handover ping-pong are **operator problems**. Hasib is a Radio
Service Specialist Engineer at Banglalink and knows their real signatures; the academic applicant
pool guesses at them. That domain knowledge is the moat, exactly as the expert question set is
the moat in `spec-rag-bench`.

It also needs **no reinforcement learning**, which is currently unclaimable — no RL policy, reward
or learning loop has ever been written. Do not quietly add one to look impressive. If RL is wanted
later it is a separate project built on this same stack, and this project is its prerequisite.

### Deliverables, in order of what actually gets read

| # | Artifact | Why it earns its place |
|---|---|---|
| 1 | `data/` — labelled KPM traces under injected faults, with a manifest | Datasets get cited; code does not |
| 2 | `RESULTS.md` — detector table, baseline vs ML, with a confusion matrix | The measurement |
| 3 | `FINDINGS.md` — one page, what failed and why | Reads as research, not a demo |
| 4 | `scripts/` — one command per scenario, pinned versions, fixed seeds | Proves rigour |
| 5 | `README.md` — architecture diagram, limitations, reproduce steps | First thing a supervisor opens |

**Not building:** a web UI, a dashboard, a hosted service, an LLM agent, a novel detection method,
a Kubernetes deployment, a fine-tune. Every hour on a frontend is an hour not on the dataset.

---

## 2. Environment and upstream facts

### Host requirements

- **Ubuntu 22.04 LTS.** Not 24.04 unless the clone's README says so — check it.
- ~8 GB RAM, ~30 GB disk, docker + docker compose v2.
- No SDR, no USRP. RF is emulated over ZeroMQ.
- If this is a VM/WSL2: give it 4+ vCPU. srsRAN gNB is real-time-ish and starves at 2.

### Components `[VERIFIED 2026-08-26]`

| Component | Source |
|---|---|
| Near-RT RIC | `https://github.com/srsran/oran-sc-ric` — "a minimal version of the O-RAN SC Near-Real-time RIC (`i-release`)", docker, **no Kubernetes or Helm** |
| gNB | `https://github.com/srsran/srsRAN_Project` — build with `cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON && make -j$(nproc)` |
| UE | srsRAN 4G `srsue`, also built with ZMQ |
| Core | Open5GS |

Service models on this path `[VERIFIED]`: **E2SM-KPM report styles 1–5**, **E2SM-RC control
service style 2**. Exposed measurements include DL/UL throughput, packet drop rates, RLC volumes.

### Stock xApps shipped in `oran-sc-ric` `[VERIFIED]`

Launched from inside the RIC compose stack:

```
docker compose up            # add --build to force rebuild, -d for background

docker compose exec python_xapp_runner ./simple_mon_xapp.py --metrics=DRB.UEThpDl,DRB.UEThpUl
docker compose exec python_xapp_runner ./kpm_mon_xapp.py --kpm_report_style=5
docker compose exec python_xapp_runner ./simple_rc_xapp.py
docker compose exec python_xapp_runner ./simple_rc_ho_xapp.py --e2_node_id gnb_001_001_0000019b --plmn 00101 --amf_ue_ngap_id 1 --target_nr_cell_id 0x19b1
docker compose exec python_xapp_runner ./simple_ccc_xapp.py
```

`kpm_mon_xapp.py` is the template to copy for our detector. **Read its source before writing
anything** — it is the ground truth for how a subscription is built on this RIC.

### Known-fragile step

Version drift between `srsRAN_Project` and `oran-sc-ric` is the single most likely thing to burn
a day: the E2 agent and the RIC must agree on E2AP/E2SM versions. If the gNB connects but no
subscription completes, that is the suspect. Pin both clones to a commit and record the two SHAs
in `NOTES.md` the moment the stack works.

---

## 3. Phases

Each phase has a **gate**. Do not start the next phase until the gate artifact exists on disk.

### P1 — Bring-up. Prove real KPM data flows. (~1–2 days)

The hard part of the whole project, and on its own already better evidence than the old lab.

1. Install docker, build deps. Clone `srsRAN_Project`, `oran-sc-ric`, srsRAN 4G, Open5GS.
2. Build srsRAN Project and srsue with the ZMQ flags above.
3. Bring up Open5GS core. `[DISCOVER]` the exact compose/config path from its own docs.
4. `docker compose up` the RIC.
5. Start gNB with E2 enabled and ZMQ radio. `[DISCOVER]` the exact config keys — the srsRAN
   tutorial config uses `"zmq"` as the radio type and enables the E2 agent; copy the sample
   config out of the clone, do not hand-write one.
6. Attach srsue. Confirm it gets an IP and can `ping` the core.
7. Run `./kpm_mon_xapp.py --kpm_report_style=1`, then generate traffic with `iperf3`.

**Gate P1:** a terminal capture showing the xApp printing **non-zero, changing** KPM values while
iperf3 runs, plus `NOTES.md` recording both repo SHAs. Zero-valued reports mean the subscription
formed but nothing is measuring — that is a failure, not a pass.

### P2 — Fault injection + dataset. (~3–4 days, this is the real work)

Turn the running stack into a repeatable experiment rig. One script per scenario, each writing a
timestamped CSV plus a JSON sidecar recording scenario name, parameters, fault window and seed.

Fault levers, in confidence order:

- **Load / PRB starvation** — ramp `iperf3` offered load past cell capacity. Reliable, verified path.
- **UE churn** — start and kill `srsue` processes on a schedule. Reliable.
- **Cell outage / sleeping cell** — needs a second cell to be interesting. `[DISCOVER]` whether
  this srsRAN build supports multiple cells or a second gNB against the same core and RIC.
  **Risk:** if multi-cell is impractical, fall back to single-cell *degradation* (gain reduction /
  bandwidth cut) and rename the project claim accordingly. Do not fake a second cell.
- **Handover ping-pong** — needs two cells plus mobility. Treat as stretch, not commitment.

Write a `scenarios/` directory: `baseline.yaml`, `load_ramp.yaml`, `ue_churn.yaml`, … Labels come
from the injector, not from eyeballing the trace afterwards — the injector knows exactly when the
fault started, so it stamps the ground truth.

Collect **at least 10 runs per scenario**, varying seed and load. A single run of each is an
anecdote and will not support any of the numbers in P3.

**Gate P2:** `data/` holds ≥40 labelled runs, a `manifest.csv` indexing them, and a plot per
scenario showing the KPI visibly moving inside the labelled fault window. If the fault is not
visible in the KPI, the fault lever does not work — fix the lever, do not ship the trace.

### P3 — The detector. (~3–4 days)

1. **Baseline first.** EWMA over the KPI plus a threshold. Tune on a held-out split.
2. **Then one ML model.** Isolation Forest or a small LSTM autoencoder. One, not three.
3. Score both: precision, recall, detection latency (seconds from fault onset to alarm),
   false alarms per hour. Latency matters more than F1 here — a detector that finds a sleeping
   cell an hour late is worthless in a real network, and saying so is the domain-expert take.
4. Split by scenario, not randomly by row. Random row splits leak across the fault window and
   inflate every number.

**A baseline that beats the ML model is a publishable result, not a failure.** That already
happened once in the old lab — the rule-based xApp beat the LLM agent — and telling it honestly
is the most persuasive thing in that repo. Lead `FINDINGS.md` with what was refuted.

**Gate P3:** `RESULTS.md` with the full table, both methods, and the confusion matrix.

### P4 — Closed loop. Optional, do only if P1–P3 are finished. (~2–3 days)

Detector fires an **E2SM-RC control action** (control service style 2 is supported), measure
recovery time against a no-control run. This is what converts "monitoring xApp" into
**"closed-loop control"**, which is the phrase in every O-RAN call for papers.

**Gate P4:** a before/after plot of the KPI with the control action marked on the time axis.

---

## 4. Repo layout

```
oran-kpm-guard/
  README.md            architecture, results summary, reproduce steps, limitations
  NOTES.md             environment deviations, pinned SHAs, dead ends
  RESULTS.md           the table
  FINDINGS.md          one page, refuted first
  setup/               install + build scripts, pinned versions
  scenarios/           one yaml per fault scenario
  xapp/                detector xApp (started from kpm_mon_xapp.py)
  collect/             run orchestration, CSV + sidecar writers
  detect/              baseline + ML, evaluation
  data/                manifest.csv + traces   (see licensing note)
  figures/
```

**Do not commit multi-GB captures.** If traces get large, commit the manifest, the derived
per-second CSVs and a `fetch_data.py`, and host the raw elsewhere. State this in the README as a
deliberate choice, not an omission.

---

## 5. Sequencing note

`README.md` gets written **last**, from `NOTES.md`. A README written on day one describes an
intention; one written from the notes describes an artifact, including the parts that did not work.

Rename `LLM-Learning` → `oran-mini-lab` before this repo goes public, and cross-link the two.
GitHub redirects the old URL permanently, so nothing breaks. This repo is also the honest
substrate for the NTN "budgeted control" spec in `docs/mini_project_ntn_oran.md` — that plan
currently reuses the self-built RIC, and would be strictly stronger rebuilt on a real E2 interface.

---

## 6. Sources

- srsRAN NearRT-RIC and xApp tutorial — https://docs.srsran.com/projects/project/en/latest/tutorials/source/near-rt-ric/source/index.html
- `srsran/oran-sc-ric` — https://github.com/srsran/oran-sc-ric
- xDevSM, portable AI-ready xApps (arXiv 2602.03821) — https://arxiv.org/html/2602.03821
- REAL: RL-enabled xApps with OSC RIC + srsRAN (arXiv 2502.00715) — https://arxiv.org/html/2502.00715v1
- LLM-Based Net Analyzer rApp for Non-RT RIC (arXiv 2603.13775) — https://arxiv.org/html/2603.13775
- Adversarial attacks on ML-based xApps (arXiv 2309.03844) — https://arxiv.org/pdf/2309.03844
- AI/ML rApp development and validation framework — https://link.springer.com/article/10.1186/s13638-026-02601-0
