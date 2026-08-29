"""From pass geometry to what the radio sees: Doppler, delay and path loss.

Every function here takes a :class:`~orbit.geometry.Pass` and a carrier frequency and
returns a time series. Nothing here knows about antennas — that is day 2's job — so
the outputs are the propagation channel only, with antenna gain left at 0 dBi.

Provenance of each term, because a figure has to be able to say which is which:

* Doppler, Doppler rate, delay      -- derived, from geometry and the speed of light.
* Free-space path loss              -- derived, Friis.
* Atmospheric gas absorption        -- cited, ITU-R P.676 zenith values, scaled by
                                       cosec(elevation). Placeholder magnitudes are
                                       flagged at runtime until read off the
                                       recommendation on day 1.
* Tropospheric scintillation        -- cited functional form (ITU-R P.618), with the
                                       amplitude left as a parameter.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from .constants import C
from .geometry import Pass


# Zenith one-way gaseous attenuation, dB, clear sky, temperate. These are
# order-of-magnitude placeholders so that the pipeline runs end to end on day 1.
# They are NOT read off ITU-R P.676 yet; `channel_profile` warns while they are in
# use, and `tasks/lessons.md` records that they must be replaced before any figure
# containing them is published.
_ZENITH_GAS_DB_PLACEHOLDER = {2.0e9: 0.035, 28.0e9: 0.30}


@dataclass
class ChannelProfile:
    """Propagation-only channel time series for one pass at one carrier."""

    t_s: np.ndarray
    elevation_deg: np.ndarray
    slant_range_m: np.ndarray
    delay_s: np.ndarray            # one-way propagation delay
    doppler_hz: np.ndarray         # positive when approaching
    doppler_rate_hz_s: np.ndarray
    fspl_db: np.ndarray
    gas_db: np.ndarray
    total_loss_db: np.ndarray
    fc_hz: float
    source: str
    gas_is_placeholder: bool

    @property
    def peak_doppler_hz(self) -> float:
        return float(np.abs(self.doppler_hz).max())

    @property
    def peak_doppler_rate_hz_s(self) -> float:
        return float(np.abs(self.doppler_rate_hz_s).max())

    @property
    def peak_delay_s(self) -> float:
        return float(self.delay_s.max())

    def at_elevation(self, elevation_deg: float) -> dict:
        """The channel state closest to a given elevation, on the approaching half.

        Used for the anchors: the plan's slant-range and delay figures are quoted at
        10 degrees, and a reader should be able to reproduce them from one call.
        """
        approaching = self.t_s <= 0.0
        idx = np.flatnonzero(approaching)
        j = idx[int(np.argmin(np.abs(self.elevation_deg[idx] - elevation_deg)))]
        return {
            "elevation_deg": float(self.elevation_deg[j]),
            "slant_range_m": float(self.slant_range_m[j]),
            "delay_s": float(self.delay_s[j]),
            "doppler_hz": float(self.doppler_hz[j]),
            "doppler_rate_hz_s": float(self.doppler_rate_hz_s[j]),
            "total_loss_db": float(self.total_loss_db[j]),
        }


def doppler_hz(range_rate_ms: np.ndarray, fc_hz: float) -> np.ndarray:
    """Doppler shift, positive while the satellite approaches.

    Range rate is positive while receding, hence the sign. The non-relativistic form
    is used: at 7.2 km/s the second-order term is 3e-10 of the carrier, which is
    150 mHz at Ka-band and far below anything this lab can measure.
    """
    return -range_rate_ms / C * fc_hz


def free_space_path_loss_db(slant_range_m: np.ndarray, fc_hz: float) -> np.ndarray:
    return 20.0 * np.log10(4.0 * np.pi * slant_range_m * fc_hz / C)


def gaseous_loss_db(elevation_deg: np.ndarray, fc_hz: float,
                    zenith_db: float | None = None) -> tuple[np.ndarray, bool]:
    """Slant-path gas absorption from a zenith value, by the cosecant law.

    Valid above roughly 5 degrees elevation; below that the flat-Earth assumption
    behind cosec(el) breaks and the true path is shorter than it predicts. This lab
    works at 10 degrees and above, so the approximation holds where it is used.
    """
    is_placeholder = zenith_db is None
    if is_placeholder:
        zenith_db = _ZENITH_GAS_DB_PLACEHOLDER.get(fc_hz)
        if zenith_db is None:
            nearest = min(_ZENITH_GAS_DB_PLACEHOLDER, key=lambda f: abs(f - fc_hz))
            zenith_db = _ZENITH_GAS_DB_PLACEHOLDER[nearest] * (fc_hz / nearest)
    el = np.radians(np.maximum(elevation_deg, 5.0))
    return zenith_db / np.sin(el), is_placeholder


def scintillation_std_db(elevation_deg: np.ndarray, fc_hz: float,
                         amplitude_db: float = 0.1) -> np.ndarray:
    """Standard deviation of tropospheric scintillation fading.

    Functional form from ITU-R P.618: the fade standard deviation scales roughly as
    f^(7/12) and as 1/sin(el)^1.2. ``amplitude_db`` sets the level at 2 GHz and
    zenith and is a parameter of the scenario, not a measurement — it is what the
    day-2 SINR margin is stressed with, and figures using it say so.
    """
    el = np.radians(np.maximum(elevation_deg, 5.0))
    return amplitude_db * (fc_hz / 2.0e9) ** (7.0 / 12.0) / np.sin(el) ** 1.2


def channel_profile(sat_pass: Pass, fc_hz: float,
                    zenith_gas_db: float | None = None) -> ChannelProfile:
    """Assemble the propagation channel for one pass at one carrier."""
    t = sat_pass.t_s
    d = sat_pass.slant_range_m

    fd = doppler_hz(sat_pass.range_rate_ms, fc_hz)

    # Doppler rate by central difference. The geometry is sampled uniformly, so a
    # gradient is exact to second order and needs no filtering. It is checked against
    # the closed form in tests/test_orbit.py.
    fd_dot = np.gradient(fd, t)

    fspl = free_space_path_loss_db(d, fc_hz)
    gas, placeholder = gaseous_loss_db(sat_pass.elevation_deg, fc_hz, zenith_gas_db)
    if placeholder:
        warnings.warn(
            "gaseous attenuation is a placeholder magnitude, not read off ITU-R P.676. "
            "Replace before publishing any figure that includes it "
            "(tasks/lessons.md 2.1).",
            stacklevel=2,
        )

    return ChannelProfile(
        t_s=t,
        elevation_deg=sat_pass.elevation_deg,
        slant_range_m=d,
        delay_s=d / C,
        doppler_hz=fd,
        doppler_rate_hz_s=fd_dot,
        fspl_db=fspl,
        gas_db=gas,
        total_loss_db=fspl + gas,
        fc_hz=fc_hz,
        source=sat_pass.source,
        gas_is_placeholder=placeholder,
    )
