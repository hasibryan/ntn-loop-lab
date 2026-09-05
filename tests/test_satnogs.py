"""Day 3: prove the harness before believing anything it says about a satellite.

Lesson 4.3 -- when a result is surprisingly bad the harness is the more likely
culprit than the algorithm -- was paid for again on day 3. The first run of
``doppler_fit`` reported a residual RMS of 262 to 502 Hz and was blamed on the
model for about a minute; the tracker was picking noise bins and, on two
captures, a second signal in the band.

Every test here plants a known answer in synthetic audio and checks the tracker
recovers it. None of them touch a real capture: a test that needs a download is a
test that stops running.
"""

from __future__ import annotations

import numpy as np
import pytest

from satnogs.doppler_fit import (
    decompose_residual,
    select_carrier,
    stationary_mode_hz,
    track_carrier,
)

FS = 48_000.0


def _tone(f_hz, dur_s=60.0, fs=FS, amp=1.0, noise=0.05, seed=0):
    """A tone at a constant or time-varying frequency, in noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur_s * fs)) / fs
    f = np.full_like(t, f_hz) if np.isscalar(f_hz) else np.asarray(f_hz)
    phase = 2.0 * np.pi * np.cumsum(f) / fs
    return amp * np.sin(phase) + rng.normal(0.0, noise, t.shape), t


# --------------------------------------------------------------------------- #
# The tracker
# --------------------------------------------------------------------------- #

def test_tracker_recovers_a_constant_tone_to_sub_bin_accuracy():
    """A 16384-point bin is 2.93 Hz. The interpolator must beat that decisively.

    Deliberately at 1234.5 Hz, which is not on a bin centre: a tone that happens
    to land on a bin is recovered exactly by the raw peak and proves nothing
    about the interpolation. Same trap as lessons.md 5.1, different instrument.
    """
    x, _ = _tone(1234.5, dur_s=40.0)
    _, f, _ = track_carrier(x, FS, band_hz=(200.0, 4000.0))
    assert len(f) > 50
    assert abs(np.median(f) - 1234.5) < 0.5


def test_tracker_follows_a_known_chirp():
    """A linear sweep, recovered slope and endpoint."""
    dur, rate = 60.0, 5.0  # Hz/s
    t = np.arange(int(dur * FS)) / FS
    x, _ = _tone(1000.0 + rate * t, dur_s=dur)
    ts, f, _ = track_carrier(x, FS, band_hz=(500.0, 2000.0))
    slope, intercept = np.polyfit(ts, f, 1)
    assert abs(slope - rate) < 0.15
    assert abs(intercept - 1000.0) < 3.0


def test_tracker_rejects_silence():
    """Noise with no carrier must not yield a confident track."""
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 1.0, int(30.0 * FS))
    _, f, _ = track_carrier(x, FS, band_hz=(200.0, 4000.0), snr_gate_db=15.0)
    # A handful of chance peaks is acceptable; a track is not.
    assert len(f) < 30


# --------------------------------------------------------------------------- #
# Separating the beacon from whatever else is in the band
# --------------------------------------------------------------------------- #

def test_selection_keeps_the_stationary_line_and_drops_the_sweeping_one():
    """The discriminator that rescued day 3, on a planted case.

    A station-corrected beacon is stationary in frequency; an uncorrected LEO
    emitter in the same band sweeps by kHz across a pass. Both are strong, so an
    SNR gate cannot tell them apart and only stationarity can.
    """
    n = 400
    t = np.linspace(0.0, 400.0, n)
    beacon = 1500.0 + 20.0 * np.sin(2 * np.pi * t / 400.0)      # +/-20 Hz wander
    sweeper = 1500.0 + 4000.0 * (t / 400.0 - 0.5)               # 4 kHz sweep
    f = np.concatenate([beacon, sweeper])
    order = np.argsort(np.concatenate([t, t]))
    f = f[order]

    assert abs(stationary_mode_hz(f) - 1500.0) < 60.0
    keep = select_carrier(f, window_hz=400.0)
    kept = f[keep]
    assert kept.size > n * 0.7           # most of the beacon survives
    assert kept.max() - kept.min() < 250.0   # the 4 kHz sweep does not


def test_a_contaminated_band_saturates_its_selection_window_and_a_clean_one_does_not():
    """The discriminator that replaced the window-ratio test on 2026-09-06.

    The ratio test was pinned at exactly 1.000 on both accepted captures -- it was
    null on the very captures it accepted. What actually separates them is how far
    the surviving population reaches towards the edge of the window it was given:
    measured 0.13 and 0.35 on the accepted pair against 1.00 and 1.00 on the
    rejected pair. A population that saturates its window is being cut by the
    window, so widening it would admit more.

    Modelled as a coherent second line, not as noise: the median continuity filter
    already drops scattered picks, and what defeats it is a strong neighbour that
    moves smoothly enough to look like a track.
    """
    window = 400.0
    rng = np.random.default_rng(3)
    n = 600
    t = np.linspace(0.0, 1.0, n)
    clean = 1500.0 + rng.normal(0.0, 15.0, n)            # a beacon and nothing else
    # A second emitter sweeping through the band, tracked in alternating frames.
    sweeper = 1500.0 + 900.0 * (t - 0.5)
    contaminated = np.where(np.arange(n) % 2 == 0, clean, sweeper)

    def fill(f):
        keep = select_carrier(f, window_hz=window)
        centre = stationary_mode_hz(f)
        kept = f[keep]
        return max(kept.max() - centre, centre - kept.min()) / window

    assert fill(clean) < 0.75
    assert fill(contaminated) >= 0.75


def test_selection_drops_isolated_noise_picks():
    t = np.arange(300)
    rng = np.random.default_rng(2)
    f = 800.0 + rng.normal(0.0, 3.0, t.shape)
    f[::15] = rng.uniform(500.0, 1100.0, f[::15].shape)  # 20 outliers
    keep = select_carrier(f, window_hz=400.0)
    assert np.std(f[keep]) < 12.0
    assert keep.sum() > 250


# --------------------------------------------------------------------------- #
# The residual decomposition
# --------------------------------------------------------------------------- #

def _synthetic_pass(n=500, dur=500.0, peak_hz=10_000.0):
    """A Doppler curve with roughly the right shape, and its rate."""
    t = np.linspace(0.0, dur, n)
    u = (t - dur / 2.0) / (dur / 8.0)
    doppler = -peak_hz * np.tanh(u)
    rate = np.gradient(doppler, t)
    return t, doppler, rate


def test_decomposition_separates_a_planted_offset_from_a_planted_time_shift():
    """The two failure signatures the plan named must not be confused.

    A receiver clock offset is a constant; a stale TLE is a time shift. Planted
    together, each must come back at its own size.
    """
    t, doppler, rate = _synthetic_pass()
    resid = 137.0 + 0.8 * rate          # 137 Hz offset, 0.8 s of time shift
    got = decompose_residual(resid, doppler, rate, t)
    assert abs(got["offset_hz"] - 137.0) < 1.0
    assert abs(got["time_shift_s"] - 0.8) < 0.02
    assert got["rms_unexplained_hz"] < 1.0


def test_decomposition_attributes_a_beacon_drift_to_drift_not_to_doppler_scale():
    """The bug this test exists for, reproduced.

    Fitted without a linear-in-time term, a beacon oscillator warming through the
    pass came back as a +5129 ppm Doppler-scale error -- half a percent of
    disagreement between two SGP4 implementations on the same TLE, which would
    have been a serious and wrong claim. With the term present it must land on
    the drift and leave the scale near zero.
    """
    t, doppler, rate = _synthetic_pass()
    drift = -0.35  # Hz/s, the size measured on KKS-1
    resid = 500.0 + drift * t
    got = decompose_residual(resid, doppler, rate, t)
    assert abs(got["beacon_drift_hz_s"] - drift) < 0.02
    assert abs(got["scale_fractional"]) < 1e-3
    assert got["rms_unexplained_hz"] < 1.0


def test_decomposition_admits_when_scale_and_drift_are_not_separable():
    """Over one pass the two are correlated, and the fit must say so.

    This is lessons.md 5.2 in a new costume: where a result rests on a split the
    data cannot make, report that it cannot be made rather than the point value.
    """
    t, doppler, rate = _synthetic_pass()
    got = decompose_residual(500.0 + 0.0 * t, doppler, rate, t)
    assert abs(got["scale_drift_correlation"]) > 0.9
    assert got["scale_separable"] is False


def test_decomposition_recovers_a_genuine_doppler_scale_error():
    """A real scale error must still be found, or the previous test is vacuous.

    Fitted here against a Doppler curve sampled over a window short enough that
    it is *not* nearly linear in time, so the two terms are distinguishable.
    """
    t, doppler, rate = _synthetic_pass(n=400, dur=140.0)
    resid = 0.004 * doppler
    got = decompose_residual(resid, doppler, rate, t)
    assert abs(got["scale_fractional"] - 0.004) < 5e-4


def test_the_reported_rms_does_not_test_the_doppler_model():
    """The null test day 3 shipped believing it was a validation.

    The SatNOGS stations remove Doppler at the receiver, so the audio carries
    ``D_true - D_station`` and this lab's model enters only as columns of the design
    matrix. ``span{1, k*d, k*d', t}`` does not depend on ``k``, so both reported
    numbers are invariant under any rescaling of the model -- including a sign flip,
    which is as wrong as a model can be. Verified on the real captures on
    2026-09-06: RMS 14.367 / 39.064 Hz and unexplained 3.966 / 6.527 Hz were
    bit-identical at x1.00, x1.10 and x-1.00.

    This test exists so the README claim cannot quietly come back. If it ever fails,
    something has made the fit sensitive to the model -- which would be good news,
    and needs the surrounding prose rewritten to match.
    """
    t, doppler, rate = _synthetic_pass()
    resid = 500.0 - 0.35 * t + 12.0 * np.sin(2 * np.pi * t / 137.0)
    base = decompose_residual(resid, doppler, rate, t)
    for k in (1.10, 0.5, -1.0):
        got = decompose_residual(resid, k * doppler, k * rate, t)
        assert got["rms_about_mean_hz"] == pytest.approx(base["rms_about_mean_hz"], rel=1e-12)
        assert got["rms_unexplained_hz"] == pytest.approx(base["rms_unexplained_hz"], rel=1e-9)


@pytest.mark.parametrize("planted", [-2.0, -0.5, 0.5, 2.0])
def test_time_shift_sign_and_size_round_trip(planted):
    """A shift is only meaningful if its sign survives. Tested away from zero,
    which is degenerate -- the same reason lessons.md 5.1 sweeps seven angles."""
    t, doppler, rate = _synthetic_pass()
    got = decompose_residual(planted * rate, doppler, rate, t)
    assert abs(got["time_shift_s"] - planted) < 0.02
