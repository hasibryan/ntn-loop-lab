"""Day 1 anchors, as tests.

The plan states values the model must reproduce before anything downstream is
trusted. Two of the plan's original values turned out to be wrong (tasks/lessons.md
1.1), which is exactly what these tests exist to catch. They now pin the corrected
values, and each one carries the closed form it was checked against by hand.

    /opt/ntnlab/venv/bin/python -m pytest tests -q
"""

import numpy as np
import pytest

from orbit.channel import channel_profile
from orbit.constants import C, R_EARTH
from orbit.geometry import (circular_pass, orbital_period_s, orbital_rate,
                            orbital_speed_ms)
from orbit.requirements import cfo_update_period_s, harq_budget_s

ALT = 600_000.0


def test_orbital_elements():
    assert orbital_period_s(ALT) / 60 == pytest.approx(96.5, abs=0.2)
    assert orbital_speed_ms(ALT) == pytest.approx(7562.0, rel=1e-3)


def test_slant_range_and_delay_at_ten_degrees():
    """Law of cosines, by hand: 1932 km, hence 6.44 ms one way."""
    p = circular_pass(ALT).visible(10.0)
    prof = channel_profile(p, 2.0e9)
    a = prof.at_elevation(10.0)
    assert a["slant_range_m"] / 1e3 == pytest.approx(1932.0, abs=5.0)
    assert a["delay_s"] * 1e3 == pytest.approx(6.44, abs=0.02)


def test_peak_doppler_depends_on_the_horizon_mask():
    """Doppler peaks at the horizon, so the mask has to be quoted with the number."""
    p = circular_pass(ALT)
    to_horizon = channel_profile(p.visible(0.0), 2.0e9).peak_doppler_hz
    masked = channel_profile(p.visible(10.0), 2.0e9).peak_doppler_hz
    assert to_horizon / 1e3 == pytest.approx(46.1, abs=0.2)
    assert masked / 1e3 == pytest.approx(45.4, abs=0.2)
    assert masked < to_horizon


def test_doppler_rate_matches_the_closed_form():
    """At closest approach the range acceleration is Re * r * omega^2 / h.

    Not v^2 / h: the satellite moves on an arc concentric with the station's radius
    vector, which costs a factor Re / r. The numerical gradient in channel.py has to
    agree with that, and the 640 Hz/s in the original plan does not.
    """
    r = R_EARTH + ALT
    omega = orbital_rate(ALT)
    d_ddot = R_EARTH * r * omega**2 / ALT       # m/s^2
    expected = d_ddot / C * 2.0e9               # Hz/s at S-band

    prof = channel_profile(circular_pass(ALT).visible(10.0), 2.0e9)
    assert expected == pytest.approx(581.0, abs=1.0)
    assert prof.peak_doppler_rate_hz_s == pytest.approx(expected, rel=2e-3)


def test_ka_scales_with_carrier():
    """Doppler and Doppler rate are both linear in carrier frequency."""
    p = circular_pass(ALT).visible(10.0)
    s = channel_profile(p, 2.0e9)
    ka = channel_profile(p, 28.0e9)
    assert ka.peak_doppler_hz / s.peak_doppler_hz == pytest.approx(14.0, rel=1e-6)
    assert ka.peak_doppler_rate_hz_s / s.peak_doppler_rate_hz_s == pytest.approx(14.0, rel=1e-6)


def test_cfo_update_period():
    """516 ms at S-band and 15 kHz SCS, from 2 % of the subcarrier spacing."""
    assert cfo_update_period_s(581.0, 15) * 1e3 == pytest.approx(516.4, abs=1.0)
    assert cfo_update_period_s(8134.0, 15) * 1e3 == pytest.approx(36.9, abs=0.5)


def test_harq_budget_brackets_the_round_trip():
    """The day-5 prediction, stated before the run.

    16 processes at 30 kHz SCS cover 8 ms, which a 12.89 ms round trip exceeds. At
    15 kHz they cover 16 ms, which it does not. If day 5 sees no difference between
    the two numerologies, the harness is wrong before the stack is.
    """
    prof = channel_profile(circular_pass(ALT).visible(10.0), 2.0e9)
    rtt = 2 * prof.peak_delay_s
    assert rtt * 1e3 == pytest.approx(12.89, abs=0.05)
    assert rtt > harq_budget_s(30)
    assert rtt < harq_budget_s(15)


def test_range_rate_is_antisymmetric_about_closest_approach():
    """A symmetric geometry must produce a symmetric Doppler curve.

    Cheap, and it catches sign and indexing mistakes that the anchors would not.
    """
    p = circular_pass(ALT, dt_s=0.1).visible(10.0)
    i0 = int(np.argmin(np.abs(p.t_s)))
    n = min(i0, len(p.t_s) - i0 - 1)
    lhs = p.range_rate_ms[i0 - n:i0]
    rhs = p.range_rate_ms[i0 + 1:i0 + 1 + n][::-1]
    assert np.allclose(lhs, -rhs, atol=1.0)
