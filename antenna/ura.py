"""Uniform rectangular array: steering, pattern, quantisation, hybrid split.

Conventions
-----------
The array lies in the xy-plane and its boresight is +z. For a ground terminal that
means boresight is the local zenith, so a satellite at elevation ``el`` sits at
polar angle ``theta = 90 - el``. Azimuth ``phi`` is measured in the array plane.

Angles are in degrees at every public boundary. Radians only appear inside a
function, never in a return value, because mixing the two is how a beamwidth ends up
57 times too large.

The element pattern is 3GPP TR 38.901 Table 7.3-1, applied rotationally symmetric
about the element boresight. The standard defines separate vertical and horizontal
cuts for a base-station element; a handheld or flat-panel terminal element is closer
to symmetric, and that substitution is a modelling choice this lab makes rather than
something the standard says. Figures that use it say so.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# TR 38.901 Table 7.3-1 element parameters.
ELEMENT_HPBW_DEG = 65.0
ELEMENT_FRONT_BACK_DB = 30.0
ELEMENT_PEAK_GAIN_DBI = 8.0


def element_pattern_db(theta_from_boresight_deg: np.ndarray) -> np.ndarray:
    """Single-element gain, dBi, against angle off the element boresight."""
    th = np.asarray(theta_from_boresight_deg, dtype=float)
    roll_off = 12.0 * (th / ELEMENT_HPBW_DEG) ** 2
    return ELEMENT_PEAK_GAIN_DBI - np.minimum(roll_off, ELEMENT_FRONT_BACK_DB)


@dataclass
class URA:
    """A uniform rectangular array of isotropically-fed patch elements.

    ``spacing`` is in wavelengths. Half-wavelength is the default because anything
    wider produces grating lobes inside the visible region once the beam is steered
    off boresight, and this array is steered to 80 degrees off boresight during a
    pass.
    """

    nx: int = 8
    ny: int = 8
    spacing: float = 0.5

    @property
    def n_elements(self) -> int:
        return self.nx * self.ny

    def positions(self) -> np.ndarray:
        """Element positions in wavelengths, shape (N, 2), centred on the origin."""
        ix = (np.arange(self.nx) - (self.nx - 1) / 2.0) * self.spacing
        iy = (np.arange(self.ny) - (self.ny - 1) / 2.0) * self.spacing
        gx, gy = np.meshgrid(ix, iy, indexing="ij")
        return np.column_stack([gx.ravel(), gy.ravel()])

    def steering_vector(self, theta_deg, phi_deg) -> np.ndarray:
        """Array response for one or many directions.

        Returns shape (N,) for scalar angles, or (..., N) matching the broadcast
        shape of the inputs.
        """
        th = np.radians(np.asarray(theta_deg, dtype=float))
        ph = np.radians(np.asarray(phi_deg, dtype=float))
        u = np.sin(th) * np.cos(ph)
        v = np.sin(th) * np.sin(ph)
        pos = self.positions()
        phase = 2.0 * np.pi * (u[..., None] * pos[:, 0] + v[..., None] * pos[:, 1])
        return np.exp(1j * phase)

    def conjugate_weights(self, theta_deg: float, phi_deg: float) -> np.ndarray:
        """Ideal unquantised phase-only weights steering the main lobe to an angle."""
        # The weight vector is the steering vector itself, NOT its conjugate. The
        # conjugation belongs in the combiner, where `response_db` applies it as
        # w^H a. Putting it here as well cancels the two and steers the beam to minus
        # the commanded angle -- which is invisible at boresight, where the angle is
        # its own negative, and only shows up once the beam is steered. It cost a
        # 56 dB carrier collapse at 83 degrees elevation before a test caught it
        # (tasks/lessons.md 5.1).
        return self.steering_vector(theta_deg, phi_deg) / np.sqrt(self.n_elements)

    def response_db(self, weights: np.ndarray, theta_deg, phi_deg,
                    include_element: bool = True, max_chunk_elements: int = 4_000_000
                    ) -> np.ndarray:
        """Total array gain, dBi, in the given directions.

        Evaluated in chunks along the angle axis. The intermediate phase array is
        ``n_angles x n_elements`` complex, so an aperture-matched Ka array of 9604
        elements over a 4001-point pattern cut is 615 MB in one allocation -- on a
        machine with 7.9 GB of RAM that is not a speed problem, it is a swap problem.
        Chunking bounds it at roughly 64 MB regardless of array size.
        """
        th = np.atleast_1d(np.asarray(theta_deg, dtype=float))
        ph = np.atleast_1d(np.asarray(phi_deg, dtype=float))
        th, ph = np.broadcast_arrays(th, ph)
        shape = th.shape
        th_f, ph_f = th.ravel(), ph.ravel()

        wc = np.conj(weights)
        step = max(1, max_chunk_elements // max(self.n_elements, 1))
        out = np.empty(th_f.size)
        for lo in range(0, th_f.size, step):
            hi = min(lo + step, th_f.size)
            a = self.steering_vector(th_f[lo:hi], ph_f[lo:hi])
            out[lo:hi] = np.abs(a @ wc) ** 2

        with np.errstate(divide="ignore"):
            g = 10.0 * np.log10(np.maximum(out, 1e-300)).reshape(shape)
        if include_element:
            g = g + element_pattern_db(th)
        return g if np.ndim(theta_deg) or np.ndim(phi_deg) else g.reshape(())


def quantise_phase(weights: np.ndarray, bits: int) -> np.ndarray:
    """Round weight phases onto a b-bit phase shifter, preserving magnitude.

    A 6-bit shifter has a 5.625 degree step. The loss this causes is small in peak
    gain and large in sidelobe level, and sidelobe level is what sets how much
    adjacent-beam interference the terminal lets in — so this is not a detail that
    can be left out of an SINR result.
    """
    if bits <= 0:
        return weights
    step = 2.0 * np.pi / (2**bits)
    mag = np.abs(weights)
    ph = np.angle(weights)
    return mag * np.exp(1j * np.round(ph / step) * step)


def hybrid_weights(array: URA, theta_deg: float, phi_deg: float,
                   n_rf: int = 4, bits: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Split a full-digital weight vector into analog phase shifters and a digital
    combiner.

    The 64 elements are partitioned into ``n_rf`` contiguous sub-arrays, each fed by
    one RF chain. Inside a sub-array the only freedom is a quantised phase shift;
    across sub-arrays the digital stage has full amplitude and phase control. This is
    the architecture that makes the day-7 CUDA problem 4x4 rather than 64x64, and it
    is why that kernel is small enough for the transfer cost to dominate.

    Returns ``(analog, digital)`` where ``analog`` is (N, n_rf) with one non-zero
    block per column, and ``digital`` is (n_rf,).
    """
    if array.n_elements % n_rf:
        raise ValueError("element count must divide evenly into RF chains")
    per_chain = array.n_elements // n_rf

    ideal = array.conjugate_weights(theta_deg, phi_deg)
    analog = np.zeros((array.n_elements, n_rf), dtype=complex)
    digital = np.zeros(n_rf, dtype=complex)

    for k in range(n_rf):
        sl = slice(k * per_chain, (k + 1) * per_chain)
        block = ideal[sl]
        # Phase-only, quantised, inside the sub-array; the mean phase of the block
        # is carried by the digital stage where it costs nothing to represent.
        ref = np.exp(1j * np.angle(block.mean())) if np.abs(block.mean()) > 0 else 1.0
        analog[sl, k] = quantise_phase(np.exp(1j * np.angle(block / ref)), bits) / np.sqrt(per_chain)
        digital[k] = ref / np.sqrt(n_rf)

    return analog, digital


def combine_hybrid(analog: np.ndarray, digital: np.ndarray) -> np.ndarray:
    """Effective element weights of a hybrid beamformer."""
    return analog @ digital


def cut_pattern(array: URA, weights: np.ndarray, phi_deg: float = 0.0,
                n: int = 4001, include_element: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """One principal cut of the pattern, from -90 to +90 degrees off boresight.

    Returned angles are signed: negative is the phi + 180 half of the cut. Sampling
    is deliberately fine, because HPBW and sidelobe level are read off this grid
    rather than from a formula, and a coarse grid quietly biases both.

    ``include_element`` selects composite gain or bare array factor. The array factor
    peaks exactly at the commanded angle; the composite peak sits inside it, because
    the element pattern is falling as the array factor rises. That difference is beam
    pulling, it is real, and `beam_pull_deg` measures it rather than hiding it.
    """
    th = np.linspace(-90.0, 90.0, n)
    phi = np.where(th >= 0, phi_deg, phi_deg + 180.0)
    return th, array.response_db(weights, np.abs(th), phi, include_element=include_element)


def beam_pull_deg(array: URA, steer_deg: float) -> float:
    """How far short of the commanded angle the composite main lobe actually lands.

    A terminal that steers open loop from ephemeris commands an angle and gets this
    one. At 8x8 with a 65 degree element it is a couple of degrees, which is a
    fraction of the 12.6 degree beamwidth and therefore a small loss -- but it is a
    systematic pointing bias, not noise, and it is worth knowing before day 9's agent
    is asked to explain a persistent SINR deficit.
    """
    phi = 0.0 if steer_deg >= 0 else 180.0
    w = array.conjugate_weights(abs(steer_deg), phi)
    th, g = cut_pattern(array, w, include_element=True)
    return float(steer_deg - th[int(np.argmax(g))])


def pattern_metrics(theta_deg: np.ndarray, gain_db: np.ndarray) -> dict:
    """Half-power beamwidth and first sidelobe level, measured off the pattern.

    Both are read from the sampled cut rather than from ``102 / N``, so that
    quantisation, element pattern and steering angle all show up in the number the
    way they show up in the hardware.
    """
    i_peak = int(np.argmax(gain_db))
    peak = float(gain_db[i_peak])
    half = peak - 3.0

    def crossing(idx_range) -> float | None:
        prev_i = i_peak
        for i in idx_range:
            if gain_db[i] <= half:
                g0, g1 = gain_db[prev_i], gain_db[i]
                t0, t1 = theta_deg[prev_i], theta_deg[i]
                if g0 == g1:
                    return float(t1)
                return float(t0 + (half - g0) * (t1 - t0) / (g1 - g0))
            prev_i = i
        return None

    lo = crossing(range(i_peak - 1, -1, -1))
    hi = crossing(range(i_peak + 1, len(gain_db)))
    hpbw = float(hi - lo) if (lo is not None and hi is not None) else float("nan")

    # First sidelobe: the highest local maximum outside the main lobe, where the main
    # lobe is bounded by the first minima either side of the peak.
    def first_min(idx_range) -> int:
        prev = gain_db[i_peak]
        last = i_peak
        for i in idx_range:
            if gain_db[i] > prev:
                return last
            prev = gain_db[i]
            last = i
        return last

    left = first_min(range(i_peak - 1, -1, -1))
    right = first_min(range(i_peak + 1, len(gain_db)))
    outside = np.concatenate([gain_db[:left + 1], gain_db[right:]])
    sll = float(outside.max() - peak) if outside.size else float("nan")

    return {
        "peak_gain_dbi": peak,
        "peak_angle_deg": float(theta_deg[i_peak]),
        "hpbw_deg": hpbw,
        "first_sll_db": sll,
    }
