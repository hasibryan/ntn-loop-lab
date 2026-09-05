"""Pass geometry: elevation, slant range and range rate against time.

Two independent sources, and that is deliberate.

``circular`` is a closed-form circular-orbit model over a non-rotating Earth. It has
no dependencies, it runs in microseconds, and every quantity it produces can be
checked by hand. It exists so that the SGP4 path has something to be wrong against.

``tle`` propagates a real two-line element set with skyfield. It is what the day-3
comparison against a recorded SatNOGS pass needs, because a real recording was made
of a real satellite whose orbit is not a textbook circle.

If the two disagree by more than a few per cent on a high-elevation pass of a
near-circular orbit, one of them is broken, and the analytic one is easier to audit.

Geometry of the analytic model
------------------------------
Let ``gamma`` be the Earth-central angle between the station and the sub-satellite
point. For a great-circle ground track passing at minimum central angle ``gamma_0``,
spherical trigonometry gives

    cos gamma(t) = cos gamma_0 * cos(omega * t)

with ``omega`` the orbital angular rate. Slant range follows from the law of cosines,

    d^2 = Re^2 + r^2 - 2 Re r cos gamma

and differentiating that, with ``gamma`` from the relation above, gives range rate in
closed form,

    d_dot = Re r omega cos(gamma_0) sin(omega t) / d

which is the quantity Doppler is computed from. Elevation comes from

    tan(el) = (cos gamma - Re / r) / sin gamma
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import MU_EARTH, R_EARTH, DEFAULT_ALTITUDE_M


@dataclass
class Pass:
    """One satellite pass, sampled uniformly in time.

    ``t`` is seconds from closest approach, so t = 0 is the point of maximum
    elevation and minimum slant range. Negative t is the approaching half, where
    range rate is negative and Doppler is positive.
    """

    t_s: np.ndarray            # s, relative to closest approach
    elevation_deg: np.ndarray  # deg above the local horizon
    slant_range_m: np.ndarray  # m
    range_rate_ms: np.ndarray  # m/s, positive receding
    altitude_m: float
    source: str                # "circular" or "tle:<name>"
    # Absolute UTC of t_s = 0, ISO-8601, for passes propagated from a TLE. The
    # analytic pass has no wall-clock epoch and leaves this None. Day 3 needs it:
    # a recorded pass has to be lined up with the audio timeline it was captured on.
    epoch_utc: str | None = None

    @property
    def max_elevation_deg(self) -> float:
        return float(self.elevation_deg.max())

    @property
    def duration_s(self) -> float:
        return float(self.t_s[-1] - self.t_s[0])

    def visible(self, min_elevation_deg: float = 0.0) -> "Pass":
        """The portion of the pass above a minimum elevation.

        A ground station has a horizon mask; below it there is no link and the
        numbers are geometry, not communications. Day 5 uses 10 degrees, which is
        the elevation the plan's slant-range anchor was computed at.
        """
        m = self.elevation_deg >= min_elevation_deg
        if not m.any():
            raise ValueError(
                f"pass never rises above {min_elevation_deg} deg "
                f"(peak {self.max_elevation_deg:.2f} deg)"
            )
        return Pass(
            t_s=self.t_s[m],
            elevation_deg=self.elevation_deg[m],
            slant_range_m=self.slant_range_m[m],
            range_rate_ms=self.range_rate_ms[m],
            altitude_m=self.altitude_m,
            source=self.source,
            epoch_utc=self.epoch_utc,
        )


def orbital_rate(altitude_m: float) -> float:
    """Angular rate of a circular orbit, rad/s."""
    r = R_EARTH + altitude_m
    return float(np.sqrt(MU_EARTH / r**3))


def orbital_period_s(altitude_m: float) -> float:
    return float(2.0 * np.pi / orbital_rate(altitude_m))


def orbital_speed_ms(altitude_m: float) -> float:
    r = R_EARTH + altitude_m
    return float(np.sqrt(MU_EARTH / r))


def horizon_central_angle(altitude_m: float) -> float:
    """Earth-central angle at which the satellite reaches the geometric horizon."""
    r = R_EARTH + altitude_m
    return float(np.arccos(R_EARTH / r))


def circular_pass(
    altitude_m: float = DEFAULT_ALTITUDE_M,
    max_elevation_deg: float = 90.0,
    dt_s: float = 0.1,
) -> Pass:
    """Closed-form pass over a non-rotating spherical Earth.

    ``max_elevation_deg`` selects which pass geometry: 90 degrees is an overhead
    pass, which maximises both Doppler rate and angular rate and is therefore the
    worst case every requirement in this lab is derived at.

    The Earth's rotation is not modelled. For a 600 km orbit that changes peak
    Doppler by a few per cent, in a direction that depends on the pass azimuth. The
    figure captions say so; the TLE path is the one to use when it matters.
    """
    r = R_EARTH + altitude_m
    omega = orbital_rate(altitude_m)

    # Central angle at closest approach that produces the requested peak elevation.
    # From tan(el) = (cos g - Re/r) / sin g, solved for g at el = el_max.
    el_max = np.radians(max_elevation_deg)
    if max_elevation_deg >= 90.0:
        gamma_0 = 0.0
    else:
        # cos(el + g) = (Re / r) cos(el) is the standard relation between elevation
        # and central angle for a spherical Earth.
        gamma_0 = float(np.arccos((R_EARTH / r) * np.cos(el_max)) - el_max)

    gamma_h = horizon_central_angle(altitude_m)
    if gamma_0 >= gamma_h:
        raise ValueError("that peak elevation never clears the horizon")

    # Time from closest approach to the horizon, from cos g_h = cos g_0 cos(w t).
    t_h = float(np.arccos(np.cos(gamma_h) / np.cos(gamma_0)) / omega)

    # Build the grid outwards from zero and mirror it, rather than stepping from
    # -t_h. The geometry is symmetric about closest approach, and a grid that is not
    # puts no sample exactly at t = 0 -- which biases the peak Doppler rate, since
    # that is precisely where it is largest.
    t_pos = np.arange(0.0, t_h, dt_s)
    t = np.concatenate([-t_pos[:0:-1], t_pos])

    cos_gamma = np.cos(gamma_0) * np.cos(omega * t)
    gamma = np.arccos(np.clip(cos_gamma, -1.0, 1.0))
    sin_gamma = np.sin(gamma)

    d = np.sqrt(R_EARTH**2 + r**2 - 2.0 * R_EARTH * r * cos_gamma)

    # Range rate. Positive while receding, which is the second half of the pass.
    d_dot = R_EARTH * r * np.cos(gamma_0) * omega * np.sin(omega * t) / d

    # Elevation. At gamma = 0 the satellite is at zenith and the expression is 0/0;
    # arctan2 handles the limit correctly because sin_gamma -> 0 from above.
    el = np.arctan2(cos_gamma - R_EARTH / r, sin_gamma)

    return Pass(
        t_s=t,
        elevation_deg=np.degrees(el),
        slant_range_m=d,
        range_rate_ms=d_dot,
        altitude_m=altitude_m,
        source="circular",
    )


def tle_pass(
    tle_path: str,
    station_lat_deg: float,
    station_lon_deg: float,
    station_alt_m: float = 0.0,
    search_hours: float = 24.0,
    dt_s: float = 0.1,
    min_elevation_deg: float = 0.0,
    t_start_utc: str | None = None,
    t_end_utc: str | None = None,
) -> Pass:
    """Propagate a real TLE and return a pass.

    With no window given, searches ``search_hours`` from the TLE epoch and returns
    the highest culmination -- the day-2 use, where any good pass will do.

    With ``t_start_utc`` and ``t_end_utc`` given (ISO-8601, UTC), the event search
    is skipped and exactly that window is sampled. Day 3 needs this: a recorded
    observation is one specific pass at one specific wall-clock time, and the
    highest pass near the TLE epoch is very probably a different one.

    skyfield is an optional dependency. Day 1 can be completed without it using the
    analytic model; day 3 cannot, because the recorded pass belongs to a specific
    satellite at a specific time.
    """
    if (t_start_utc is None) != (t_end_utc is None):
        raise ValueError("give both t_start_utc and t_end_utc, or neither")
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "skyfield is needed for TLE propagation: "
            "/opt/ntnlab/venv/bin/pip install skyfield"
        ) from exc

    with open(tle_path, "r", encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    if len(lines) < 2:
        raise ValueError(f"{tle_path} does not contain a two-line element set")
    name, l1, l2 = (lines[0], lines[1], lines[2]) if len(lines) >= 3 else ("sat", lines[0], lines[1])

    ts = load.timescale()
    sat = EarthSatellite(l1, l2, name, ts)
    station = wgs84.latlon(station_lat_deg, station_lon_deg, elevation_m=station_alt_m)

    if t_start_utc is not None:
        # An explicit window. Sample it as given; no event search, no pass selection.
        from datetime import datetime, timezone

        def _utc(s: str) -> datetime:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

        t_a, t_b = _utc(t_start_utc), _utc(t_end_utc)
        span_s = (t_b - t_a).total_seconds()
        if span_s <= 0:
            raise ValueError(f"empty window: {t_start_utc} to {t_end_utc}")
        n = int(round(span_s / dt_s)) + 1
        offsets = np.arange(n) * dt_s
        t_anchor = ts.from_datetime(t_a)
        tt = ts.tt_jd(t_anchor.tt + offsets / 86400.0)
    else:
        t0 = ts.tt_jd(sat.epoch.tt)
        t1 = ts.tt_jd(sat.epoch.tt + search_hours / 24.0)
        times, events = sat.find_events(station, t0, t1, altitude_degrees=min_elevation_deg)

        # Pick the pass with the highest culmination: a high pass gives the cleanest
        # Doppler curve and the largest angular rate, which is what day 2 needs.
        best = None
        for i, ev in enumerate(events):
            if ev != 1:  # 1 = culminate
                continue
            alt, _, _ = (sat - station).at(times[i]).altaz()
            if best is None or alt.degrees > best[1]:
                best = (times[i], alt.degrees)
        if best is None:
            raise ValueError(f"no pass above {min_elevation_deg} deg within {search_hours} h of epoch")

        t_anchor = best[0]
        half = 900.0  # s, generous half-window; trimmed by .visible() afterwards
        offsets = np.arange(-half, half + dt_s, dt_s)
        tt = ts.tt_jd(t_anchor.tt + offsets / 86400.0)

    topo = (sat - station).at(tt)
    alt, _, dist = topo.altaz()
    # Range rate from the relative position and velocity, projected on the line of
    # sight. Differentiating the range numerically would work but loses precision at
    # 0.1 s spacing near closest approach.
    pos = topo.position.m           # 3 x N
    vel = topo.velocity.m_per_s     # 3 x N
    rng = np.linalg.norm(pos, axis=0)
    d_dot = np.sum(pos * vel, axis=0) / rng

    # Re-reference time to closest approach so that the analytic and TLE passes share
    # a convention and can be plotted on the same axes.
    i0 = int(np.argmin(rng))
    mean_motion_rev_per_day = float(sat.model.no_kozai) * 1440.0 / (2.0 * np.pi)
    period_s = 86400.0 / mean_motion_rev_per_day
    semi_major = (MU_EARTH * (period_s / (2.0 * np.pi)) ** 2) ** (1.0 / 3.0)

    return Pass(
        t_s=offsets - offsets[i0],
        elevation_deg=alt.degrees,
        slant_range_m=rng,
        range_rate_ms=d_dot,
        altitude_m=float(semi_major - R_EARTH),
        source=f"tle:{name}",
        epoch_utc=tt[i0].utc_iso(),
    )
