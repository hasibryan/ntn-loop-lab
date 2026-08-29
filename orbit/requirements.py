"""The load-bearing derivation: how fast must each control loop run?

This module turns pass geometry into the x-axis of Figure 0. Nothing here is
measured — every number is derived from the channel profile and a stated budget —
and every figure that uses it says so.

Three requirements come out, one per tier:

``cfo_update_period``   the microsecond tier. Open-loop Doppler pre-compensation from
                        ephemeris is applied at discrete instants; between them the
                        residual offset grows at the Doppler rate. The period is set
                        by how much of the subcarrier spacing the residual may eat.

``beam_dwell``          the millisecond tier. How long the satellite stays inside one
                        beam of the array, which is what bounds how often beam or
                        satellite selection has to be revisited. Needs the array
                        beamwidth, so it is completed on day 2.

``control_staleness``   also the millisecond tier, and the one that is specific to
                        NTN. A measurement reaching the RIC is already one propagation
                        delay old, and the resulting action arrives one propagation
                        delay late. On a terrestrial link that is microseconds and
                        invisible. At 600 km it is a round trip of up to 12.9 ms,
                        which is the same order as the Near-RT RIC's own budget. The
                        loop does not fail because it is slow; it fails because it is
                        looking at the past and acting on the future.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .channel import ChannelProfile
from .constants import CFO_BUDGET_FRACTION, N_HARQ, SCS_HZ, SLOT_S

# O-RAN's specified control-loop budgets, cited. These are what the measurements on
# days 6, 7, 11 and 12 are compared against; they are not measurements themselves.
TIER_BUDGET_S = {
    "L1": (1e-6, 1e-3),
    "Near-RT RIC": (10e-3, 1.0),
    "Non-RT RIC": (1.0, float("inf")),
}


@dataclass
class LoopRequirement:
    """One row of the requirement table."""

    band: str
    fc_hz: float
    scs_khz: int
    cfo_budget_hz: float
    peak_doppler_hz: float
    peak_doppler_rate_hz_s: float
    cfo_update_period_s: float
    peak_one_way_delay_s: float
    round_trip_s: float
    harq_budget_s: float
    harq_stalls: bool
    tier_for_cfo_loop: str

    def as_dict(self) -> dict:
        return asdict(self)


def tier_for(period_s: float) -> str:
    """Which O-RAN tier can service a loop of this period.

    Returns the fastest tier whose budget contains the period. A loop faster than
    every tier's lower bound has to live in the datapath, which is the answer this
    project expects for Doppler pre-compensation.
    """
    for name, (lo, hi) in TIER_BUDGET_S.items():
        if lo <= period_s <= hi:
            return name
    if period_s < TIER_BUDGET_S["L1"][0]:
        return "datapath (faster than L1 budget)"
    return "Non-RT RIC"


def cfo_update_period_s(peak_doppler_rate_hz_s: float, scs_khz: int,
                        budget_fraction: float = CFO_BUDGET_FRACTION) -> float:
    """Longest interval between open-loop Doppler corrections.

    Between corrections the residual offset grows linearly at the Doppler rate, so
    the residual at the end of an interval of length T is |f_dot| * T. Holding that
    under a fraction of the subcarrier spacing gives

        T <= budget_fraction * SCS / |f_dot|_max

    This is first order and therefore conservative in the right direction: it ignores
    curvature in the Doppler profile, which only makes the true residual smaller
    away from closest approach.
    """
    return budget_fraction * SCS_HZ[scs_khz] / peak_doppler_rate_hz_s


def harq_budget_s(scs_khz: int, n_processes: int = N_HARQ) -> float:
    """Round-trip time a HARQ process pool can cover before it stalls.

    With ``n`` processes and one transmission per slot, a transmitter can keep the
    pipe full for ``n`` slots while waiting for the first acknowledgement. Beyond
    that it has nothing left to send and throughput collapses. This is the prediction
    day 5 sweeps against; it is stated here, before the run.
    """
    return n_processes * SLOT_S[scs_khz]


def requirement_table(profiles: dict[str, ChannelProfile],
                      scs_list: tuple[int, ...] = (15, 30)) -> list[LoopRequirement]:
    """Build the full requirement table across bands and numerologies."""
    rows: list[LoopRequirement] = []
    for band, prof in profiles.items():
        for scs in scs_list:
            t_cfo = cfo_update_period_s(prof.peak_doppler_rate_hz_s, scs)
            rtt = 2.0 * prof.peak_delay_s
            budget = harq_budget_s(scs)
            rows.append(
                LoopRequirement(
                    band=band,
                    fc_hz=prof.fc_hz,
                    scs_khz=scs,
                    cfo_budget_hz=CFO_BUDGET_FRACTION * SCS_HZ[scs],
                    peak_doppler_hz=prof.peak_doppler_hz,
                    peak_doppler_rate_hz_s=prof.peak_doppler_rate_hz_s,
                    cfo_update_period_s=t_cfo,
                    peak_one_way_delay_s=prof.peak_delay_s,
                    round_trip_s=rtt,
                    harq_budget_s=budget,
                    harq_stalls=rtt > budget,
                    tier_for_cfo_loop=tier_for(t_cfo),
                )
            )
    return rows


def control_staleness_s(profile: ChannelProfile, elevation_deg: float = 10.0) -> dict:
    """Irreducible age of a Near-RT control decision, from propagation alone.

    A measurement is one one-way delay old when the RIC sees it. The action is one
    one-way delay late when it lands. Neither has anything to do with how fast the
    RIC computes, which is why this floor cannot be engineered away by a faster xApp
    and has to be designed around instead.
    """
    state = profile.at_elevation(elevation_deg)
    one_way = state["delay_s"]
    return {
        "elevation_deg": state["elevation_deg"],
        "measurement_age_s": one_way,
        "action_lateness_s": one_way,
        "total_staleness_s": 2.0 * one_way,
        "near_rt_budget_lo_s": TIER_BUDGET_S["Near-RT RIC"][0],
        "fraction_of_fastest_near_rt_loop": 2.0 * one_way / TIER_BUDGET_S["Near-RT RIC"][0],
    }


def format_table(rows: list[LoopRequirement]) -> str:
    """The requirement table as it appears in the paper and the day-1 log."""
    head = (
        f"{'band':<5} {'SCS':>5} {'peak f_d':>12} {'peak df/dt':>12} "
        f"{'CFO budget':>11} {'update period':>14} {'tier':>28}"
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r.band:<5} {r.scs_khz:>3} kHz "
            f"{r.peak_doppler_hz / 1e3:>9.2f} kHz "
            f"{r.peak_doppler_rate_hz_s:>9.1f} Hz/s "
            f"{r.cfo_budget_hz:>8.0f} Hz "
            f"{r.cfo_update_period_s * 1e3:>11.2f} ms "
            f"{r.tier_for_cfo_loop:>28}"
        )
    return "\n".join(lines)
