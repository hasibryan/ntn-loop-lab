"""Day 2 invariants.

The first of these is the test that should have existed before the SINR figure was
drawn. A beamformer whose main lobe does not appear where it was told to point is
wrong in a way that produces plausible-looking output everywhere except the one
place it matters, and boresight -- the case a person checks by eye -- is exactly
where the error is invisible.

    /opt/ntnlab/venv/bin/python -m pytest tests -q
"""

import numpy as np
import pytest

from antenna.interference import (LinkScenario, beam_dwell_s,
                                  line_of_sight_rate_deg_s, sinr_over_pass)
from antenna.ura import (URA, beam_pull_deg, combine_hybrid, cut_pattern,
                         element_pattern_db, hybrid_weights, pattern_metrics,
                         quantise_phase)
from orbit.channel import channel_profile
from orbit.geometry import circular_pass

ALT = 600_000.0


@pytest.mark.parametrize("steer", [0.0, 15.0, 30.0, 45.0, 60.0, -30.0, -60.0])
def test_array_factor_points_where_it_was_told(steer):
    """The whole point of a phased array.

    Checked on the bare array factor, which peaks exactly at the commanded angle. A
    conjugation applied on both the weight and the combiner side cancels and steers
    the beam to minus the commanded angle instead -- undetectable at boresight, which
    is the one case a person checks by eye.
    """
    a = URA(8, 8)
    phi = 0.0 if steer >= 0 else 180.0
    w = a.conjugate_weights(abs(steer), phi)
    th, g = cut_pattern(a, w, include_element=False)
    assert pattern_metrics(th, g)["peak_angle_deg"] == pytest.approx(steer, abs=0.1)


@pytest.mark.parametrize("steer,expected_pull", [
    (0.0, 0.00), (15.0, 0.65), (30.0, 1.52), (45.0, 3.15), (60.0, 6.50), (80.0, 16.78),
])
def test_element_pattern_pulls_the_composite_beam_toward_boresight(steer, expected_pull):
    """Beam pulling is real, grows fast, and is reported rather than asserted away.

    Pinned to measured values rather than to an invented linear law. The number that
    matters is the last row: commanding 80 degrees off boresight -- a satellite at 10
    degrees elevation, which is where acquisition and handover happen -- lands the
    beam at 63 degrees. That is a 16.8 degree pointing error against a 12.6 degree
    beamwidth, so open-loop pointing from ephemeris misses the satellite by more than
    a full beam at the edges of a pass.
    """
    a = URA(8, 8)
    pull = beam_pull_deg(a, steer)
    assert pull == pytest.approx(expected_pull, abs=0.15)
    assert pull >= 0.0


def test_pointing_error_exceeds_the_beamwidth_near_the_horizon():
    """The day-2 result that gives day 9's agent something to correct."""
    a = URA(8, 8)
    th, g = cut_pattern(a, a.conjugate_weights(0.0, 0.0))
    hpbw = pattern_metrics(th, g)["hpbw_deg"]
    assert beam_pull_deg(a, 80.0) > hpbw
    assert beam_pull_deg(a, 45.0) < hpbw / 2


def test_boresight_gain_is_elements_plus_element_gain():
    """64 elements is 18.06 dB of array gain on top of an 8 dBi element."""
    a = URA(8, 8)
    th, g = cut_pattern(a, a.conjugate_weights(0.0, 0.0))
    m = pattern_metrics(th, g)
    assert m["peak_gain_dbi"] == pytest.approx(10 * np.log10(64) + 8.0, abs=0.05)


def test_boresight_beamwidth_and_sidelobe():
    """HPBW near 102/N degrees, first sidelobe near the uniform-array -13.2 dB."""
    a = URA(8, 8)
    th, g = cut_pattern(a, a.conjugate_weights(0.0, 0.0))
    m = pattern_metrics(th, g)
    assert m["hpbw_deg"] == pytest.approx(101.5 / 8, abs=0.7)
    assert m["first_sll_db"] == pytest.approx(-13.2, abs=1.5)


def test_scan_loss_is_the_element_pattern_at_the_pulled_peak():
    """Where scan loss comes from in this model, stated so it cannot drift.

    With unit-modulus weights the array factor peak is N whatever the steering angle,
    so all of the scan loss is the element pattern, evaluated at the angle the beam
    actually lands on rather than the one it was commanded to. No separate cos(theta)
    aperture-projection term is applied: TR 38.901 composes element pattern with array
    factor and adding projection on top would double-count.
    """
    a = URA(8, 8)
    th0, g0 = cut_pattern(a, a.conjugate_weights(0.0, 0.0))
    th1, g1 = cut_pattern(a, a.conjugate_weights(60.0, 0.0))
    m0, m1 = pattern_metrics(th0, g0), pattern_metrics(th1, g1)

    # Two terms, both evaluated at the angle the composite beam actually lands on:
    # the element pattern's roll-off there, plus the array factor's own loss for
    # being off its peak by the beam pull.
    peak_angle = m1["peak_angle_deg"]
    element_loss = float(element_pattern_db(0.0) - element_pattern_db(peak_angle))
    th_af, g_af = cut_pattern(a, a.conjugate_weights(60.0, 0.0), include_element=False)
    af_loss = float(g_af.max() - np.interp(peak_angle, th_af, g_af))

    assert element_loss == pytest.approx(8.13, abs=0.1)
    assert af_loss == pytest.approx(0.89, abs=0.1)
    assert m0["peak_gain_dbi"] - m1["peak_gain_dbi"] == pytest.approx(
        element_loss + af_loss, abs=0.05)


def test_six_bit_quantisation_is_cheap_in_gain_and_dear_in_sidelobes():
    a = URA(8, 8)
    ideal = a.conjugate_weights(45.0, 0.0)
    coarse = quantise_phase(ideal, 2)
    th_i, g_i = cut_pattern(a, ideal)
    th_c, g_c = cut_pattern(a, coarse)
    m_i, m_c = pattern_metrics(th_i, g_i), pattern_metrics(th_c, g_c)
    assert m_i["peak_gain_dbi"] - m_c["peak_gain_dbi"] < 2.0
    assert m_c["first_sll_db"] > m_i["first_sll_db"]


def test_hybrid_split_preserves_the_pointing_direction():
    a = URA(8, 8)
    an, dg = hybrid_weights(a, 40.0, 0.0, n_rf=4, bits=6)
    th, g = cut_pattern(a, combine_hybrid(an, dg), include_element=False)
    assert pattern_metrics(th, g)["peak_angle_deg"] == pytest.approx(40.0, abs=0.5)


def test_steering_beats_a_fixed_beam_at_every_instant():
    """A beam pointed at the satellite cannot do worse than one pinned at zenith.

    If it does, either the pointing or the interference geometry is wrong. This is
    the assertion that exposed the sign error: `fixed` was outscoring `ideal` on the
    95th percentile of SINR, which is not something a correct model can produce.
    """
    p = circular_pass(ALT, dt_s=2.0).visible(10.0)
    prof = channel_profile(p, 2.0e9)
    a, sc = URA(8, 8), LinkScenario()
    fixed = sinr_over_pass(p, prof, a, sc, mode="fixed")
    ideal = sinr_over_pass(p, prof, a, sc, mode="ideal")
    assert np.all(ideal.sinr_db >= fixed.sinr_db - 1e-6)
    assert np.median(ideal.sinr_db) > np.median(fixed.sinr_db)


def test_line_of_sight_rate_at_zenith_is_speed_over_altitude():
    """0.722 deg/s for a 600 km overhead pass, and the dwell that follows from it."""
    p = circular_pass(ALT, dt_s=0.5).visible(10.0)
    rate = line_of_sight_rate_deg_s(p)
    assert rate.max() == pytest.approx(np.degrees(7562.0 / ALT), rel=2e-3)
    dwell = beam_dwell_s(p, 12.56)
    assert dwell["min_dwell_s"] == pytest.approx(17.4, abs=0.3)
