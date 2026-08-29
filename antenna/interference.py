"""Link budget, co-channel interference from the rest of the constellation, and the
angular rate that sets how often a beam has to be re-pointed.

The interference model is not a set of invented angles. Co-channel interferers are
the *same* satellite track, offset in time by the in-plane spacing of the
constellation: a satellite one slot ahead is, by construction, where the serving
satellite was ``spacing_s`` seconds ago. That makes the geometry self-consistent
with day 1 at the cost of exactly one parameter, and it means interference appears
and disappears over the pass the way it actually does.

Everything here is derived or parametric. The EIRP and system-temperature defaults
are scenario parameters, not measurements, and any figure that uses them says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from orbit.channel import ChannelProfile
from orbit.constants import C
from orbit.geometry import Pass, orbital_speed_ms
from .ura import URA

BOLTZMANN_DBW_HZ_K = -228.6  # dB(W/Hz/K), 10 log10(k)


@dataclass
class LinkScenario:
    """Parameters of the downlink. All of these are scenario, none are measured."""

    eirp_dbw: float = 34.0          # per beam, satellite side
    t_system_k: float = 250.0       # terminal system noise temperature
    bandwidth_hz: float = 10.0e6    # matches the srsRAN carrier used on day 4
    inplane_spacing_s: float = 263.0  # 22 satellites in a 96.5 min plane
    n_interferer_slots: int = 3     # how many neighbours either side to consider
    min_elevation_deg: float = 10.0
    phase_bits: int = 6
    n_rf_chains: int = 4

    # Satellite-side beam discrimination toward a terminal outside the neighbour's
    # own cell. Without this term every neighbour is modelled as pointing its full
    # EIRP at this terminal, which is not what a multi-beam constellation does: the
    # neighbour is serving its own cell and this terminal sees its beam roll-off.
    #
    # The first version of this model omitted the term. It produced a median SINR of
    # -3 dB and ranked an unsteered beam above a steered one, which is how the
    # omission was caught. 25 dB is a scenario parameter, not a measurement, so the
    # day-2 output sweeps it rather than asserting it.
    sat_beam_discrimination_db: float = 25.0

    def noise_dbw(self) -> float:
        return BOLTZMANN_DBW_HZ_K + 10.0 * np.log10(self.t_system_k * self.bandwidth_hz)


@dataclass
class SinrResult:
    t_s: np.ndarray
    elevation_deg: np.ndarray
    carrier_dbw: np.ndarray
    interference_dbw: np.ndarray
    noise_dbw: float
    sinr_db: np.ndarray
    n_visible_interferers: np.ndarray
    label: str
    metrics: dict = field(default_factory=dict)


def line_of_sight_rate_deg_s(sat_pass: Pass) -> np.ndarray:
    """Angular rate of the satellite in the terminal's local frame, deg/s.

    The transverse component of the relative velocity divided by the slant range.
    Radial motion moves the satellite closer, not sideways, so it is removed first:
    ``v_t = sqrt(v^2 - r_dot^2)``. At closest approach on an overhead pass the radial
    term vanishes and the rate is simply orbital speed over altitude.
    """
    v = orbital_speed_ms(sat_pass.altitude_m)
    v_t = np.sqrt(np.maximum(v**2 - sat_pass.range_rate_ms**2, 0.0))
    return np.degrees(v_t / sat_pass.slant_range_m)


def beam_dwell_s(sat_pass: Pass, hpbw_deg: float) -> dict:
    """How long the satellite stays inside one beam, and what that demands.

    The beam has to be revisited before the satellite leaves it, so the shortest
    dwell over the pass is the requirement. This is the millisecond tier's entry in
    Figure 0 — or, as day 2 turns out to show, not the millisecond tier at all.
    """
    rate = line_of_sight_rate_deg_s(sat_pass)
    peak_rate = float(rate.max())
    return {
        "peak_los_rate_deg_s": peak_rate,
        "hpbw_deg": hpbw_deg,
        "min_dwell_s": hpbw_deg / peak_rate,
        "mean_dwell_s": hpbw_deg / float(rate.mean()),
    }


def elements_per_side_for_dwell(sat_pass: Pass, target_dwell_s: float,
                                spacing: float = 0.5) -> float:
    """How large the array would have to be before dwell hit a target period.

    Uses the standard uniform-array beamwidth ``0.886 * lambda / (N d)``, inverted.
    Answering "what would it take for beam tracking alone to need a fast loop" is
    more useful than asserting that it does.
    """
    peak_rate = float(line_of_sight_rate_deg_s(sat_pass).max())
    hpbw_needed = target_dwell_s * peak_rate
    return float(np.degrees(0.886 / spacing) / hpbw_needed)


def _offset_state(sat_pass: Pass, shift_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Elevation and slant range of a satellite ``shift_s`` behind on the same track.

    Outside the sampled pass the neighbour is below the horizon; elevation is
    returned as -90 there so the visibility mask removes it.
    """
    el = np.interp(sat_pass.t_s + shift_s, sat_pass.t_s, sat_pass.elevation_deg,
                   left=-90.0, right=-90.0)
    d = np.interp(sat_pass.t_s + shift_s, sat_pass.t_s, sat_pass.slant_range_m,
                  left=np.nan, right=np.nan)
    return el, d


@dataclass
class BeamGains:
    """Antenna gains over a pass, before any link budget is applied.

    Separated from the budget because the two have different costs and different
    dependencies. Gains take a pattern evaluation per sample per direction and depend
    only on the array, the geometry and the beamforming mode. The budget is arithmetic
    and depends on EIRP, noise temperature and beam discrimination. Sweeping a budget
    parameter therefore costs nothing once the gains exist -- which is what makes the
    day-2 sensitivity sweep affordable on a 9604-element array.
    """

    t_s: np.ndarray
    elevation_deg: np.ndarray
    theta_serving_deg: np.ndarray
    g_serving_db: np.ndarray
    interferers: list           # (g_db, slant_range_m, visible) per neighbour
    mode: str
    metrics: dict


def beam_gains_over_pass(sat_pass: Pass, array: URA, scenario: LinkScenario,
                         mode: str = "ideal") -> BeamGains:
    """The expensive half: what the array does, sample by sample.

    ``mode`` is one of:

    ``fixed``      the beam is pointed at zenith and never moves. The control arm.
    ``ideal``      unquantised steering weights, re-pointed every sample.
    ``quantised``  the same, through 6-bit analog phase shifters in a hybrid
                   N-element, 4-chain architecture. This is the realisable one, and
                   the gap between it and ``ideal`` is what a hardware budget costs.
    """
    from .ura import combine_hybrid, cut_pattern, hybrid_weights, pattern_metrics

    # Signed off-boresight angle. The pass crosses zenith, so after closest approach
    # the satellite is on the opposite side of the sky, at azimuth 180 rather than 0.
    # Tracking that sign is not cosmetic: steering the whole pass to azimuth 0 points
    # the beam at the mirror image for the second half, which is how the first version
    # of this function managed to rank a fixed zenith beam above a steered one on the
    # 95th percentile of SINR.
    u_serving = -np.sign(sat_pass.t_s) * (90.0 - sat_pass.elevation_deg)
    theta_serving = np.abs(u_serving)
    phi_serving = np.where(u_serving >= 0.0, 0.0, 180.0)
    n = len(sat_pass.t_s)

    # Interferer geometry: same ground track, offset by whole constellation slots. A
    # neighbour ``s`` seconds behind is where the serving satellite was ``s`` seconds
    # ago, so its side of the sky follows from the sign of its own effective time.
    shifts = [k * scenario.inplane_spacing_s
              for k in range(-scenario.n_interferer_slots, scenario.n_interferer_slots + 1)
              if k != 0]
    interferers = []
    for s in shifts:
        el, d = _offset_state(sat_pass, s)
        visible = (el >= scenario.min_elevation_deg) & np.isfinite(d)
        if visible.any():
            u_i = -np.sign(sat_pass.t_s + s) * (90.0 - el)
            interferers.append((np.abs(u_i), np.where(u_i >= 0.0, 0.0, 180.0), d, visible))

    g_serving = np.empty(n)
    g_interf = [np.full(n, -np.inf) for _ in interferers]

    for i in range(n):
        if mode == "fixed":
            w = array.conjugate_weights(0.0, 0.0)
        elif mode == "ideal":
            w = array.conjugate_weights(theta_serving[i], phi_serving[i])
        elif mode == "quantised":
            a, dg = hybrid_weights(array, theta_serving[i], phi_serving[i],
                                   n_rf=scenario.n_rf_chains, bits=scenario.phase_bits)
            w = combine_hybrid(a, dg)
        else:
            raise ValueError(f"unknown mode {mode!r}")

        g_serving[i] = float(array.response_db(w, theta_serving[i], phi_serving[i]))

        for k, (theta_i, phi_i, d, visible) in enumerate(interferers):
            if visible[i]:
                g_interf[k][i] = float(array.response_db(w, theta_i[i], phi_i[i]))

    # Pattern metrics at the hardest steering angle of the pass, which is the horizon.
    theta_worst = float(theta_serving.max())
    if mode == "quantised":
        a, dg = hybrid_weights(array, theta_worst, 0.0,
                               n_rf=scenario.n_rf_chains, bits=scenario.phase_bits)
        w_worst = combine_hybrid(a, dg)
    else:
        w_worst = array.conjugate_weights(0.0 if mode == "fixed" else theta_worst, 0.0)
    th, g = cut_pattern(array, w_worst)
    metrics = pattern_metrics(th, g)
    metrics["steered_to_deg"] = theta_worst

    return BeamGains(
        t_s=sat_pass.t_s,
        elevation_deg=sat_pass.elevation_deg,
        theta_serving_deg=theta_serving,
        g_serving_db=g_serving,
        interferers=[(g_interf[k], interferers[k][2], interferers[k][3])
                     for k in range(len(interferers))],
        mode=mode,
        metrics=metrics,
    )


def sinr_from_gains(gains: BeamGains, profile: ChannelProfile,
                    scenario: LinkScenario) -> SinrResult:
    """The cheap half: apply a link budget to gains that already exist."""
    carrier = scenario.eirp_dbw + gains.g_serving_db - profile.total_loss_db

    interf_lin = np.zeros_like(carrier)
    n_vis = np.zeros(carrier.size, dtype=int)
    for g_db, d, visible in gains.interferers:
        fspl = 20.0 * np.log10(4.0 * np.pi * np.where(visible, d, 1.0) * profile.fc_hz / C)
        p_i = (scenario.eirp_dbw - scenario.sat_beam_discrimination_db + g_db - fspl)
        interf_lin += np.where(visible, 10.0 ** (p_i / 10.0), 0.0)
        n_vis += visible.astype(int)

    noise = scenario.noise_dbw()
    sinr = carrier - 10.0 * np.log10(interf_lin + 10.0 ** (noise / 10.0))
    with np.errstate(divide="ignore"):
        interf_dbw = 10.0 * np.log10(np.maximum(interf_lin, 1e-300))

    return SinrResult(
        t_s=gains.t_s,
        elevation_deg=gains.elevation_deg,
        carrier_dbw=carrier,
        interference_dbw=interf_dbw,
        noise_dbw=noise,
        sinr_db=sinr,
        n_visible_interferers=n_vis,
        label=gains.mode,
        metrics=gains.metrics,
    )


def sinr_over_pass(sat_pass: Pass, profile: ChannelProfile, array: URA,
                   scenario: LinkScenario, mode: str = "ideal",
                   gains: BeamGains | None = None) -> SinrResult:
    """SINR against time for one beamforming strategy.

    Pass ``gains`` to reuse a previous `beam_gains_over_pass` result when only budget
    parameters have changed.
    """
    if gains is None or gains.mode != mode:
        gains = beam_gains_over_pass(sat_pass, array, scenario, mode=mode)
    return sinr_from_gains(gains, profile, scenario)
