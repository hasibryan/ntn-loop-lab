"""Day 1 entry point: build the channel time series and the requirement table.

    make orbit                 # both bands, analytic overhead pass
    make orbit BAND=ka
    python -m orbit.pass_profile --source tle --tle orbit/tle/sat.tle \
                                 --lat 39.33 --lon -76.62

Writes ``data/ntn_channel_<band>.npz`` for day 2 and day 4 to consume, prints the
requirement table, and draws Figure 1.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np

from .channel import channel_profile
from .constants import BANDS, DEFAULT_ALTITUDE_M
from .geometry import (circular_pass, orbital_period_s, orbital_speed_ms,
                       tle_pass)
from .requirements import (control_staleness_s, format_table, requirement_table)

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
FIGURES = REPO / "eval" / "figures"


def build(args) -> dict:
    if args.source == "tle":
        if not args.tle:
            raise SystemExit("--source tle needs --tle pointing at a two-line element set")
        sat_pass = tle_pass(
            args.tle, args.lat, args.lon,
            station_alt_m=args.station_alt, dt_s=args.dt,
            min_elevation_deg=args.min_elevation,
        )
    else:
        sat_pass = circular_pass(
            altitude_m=args.altitude, max_elevation_deg=args.max_elevation, dt_s=args.dt
        )
    sat_pass = sat_pass.visible(args.min_elevation)

    profiles = {}
    for band in args.bands:
        profiles[band] = channel_profile(sat_pass, BANDS[band]["fc_hz"])
    return {"pass": sat_pass, "profiles": profiles}


def save(sat_pass, profiles) -> list[Path]:
    DATA.mkdir(parents=True, exist_ok=True)
    written = []
    for band, p in profiles.items():
        out = DATA / f"ntn_channel_{band}.npz"
        np.savez_compressed(
            out,
            t_s=p.t_s,
            elevation_deg=p.elevation_deg,
            slant_range_m=p.slant_range_m,
            delay_s=p.delay_s,
            doppler_hz=p.doppler_hz,
            doppler_rate_hz_s=p.doppler_rate_hz_s,
            fspl_db=p.fspl_db,
            gas_db=p.gas_db,
            total_loss_db=p.total_loss_db,
            range_rate_ms=sat_pass.range_rate_ms,
            fc_hz=p.fc_hz,
            altitude_m=sat_pass.altitude_m,
            source=p.source,
            gas_is_placeholder=p.gas_is_placeholder,
        )
        written.append(out)
    return written


def figure_1(sat_pass, profiles) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(4, 1, figsize=(7.2, 9.0), sharex=True)
    t = sat_pass.t_s

    ax[0].plot(t, sat_pass.elevation_deg, color="k")
    ax[0].set_ylabel("elevation (deg)")
    ax[0].grid(alpha=0.3)

    ax[1].plot(t, sat_pass.slant_range_m / 1e3, color="k")
    ax[1].set_ylabel("slant range (km)")
    ax[1].grid(alpha=0.3)

    styles = {"s": ("-", "tab:blue"), "ka": ("--", "tab:red")}
    for band, p in profiles.items():
        ls, col = styles.get(band, ("-", "k"))
        ax[2].plot(t, p.doppler_hz / 1e3, ls, color=col, label=BANDS[band]["label"])
        ax[3].plot(t, p.doppler_rate_hz_s / 1e3, ls, color=col, label=BANDS[band]["label"])
    ax[2].set_ylabel("Doppler (kHz)")
    ax[2].legend(fontsize=8)
    ax[2].grid(alpha=0.3)
    ax[3].set_ylabel("Doppler rate (kHz/s)")
    ax[3].set_xlabel("time from closest approach (s)")
    ax[3].legend(fontsize=8)
    ax[3].grid(alpha=0.3)

    alt_km = sat_pass.altitude_m / 1e3
    fig.suptitle(
        f"Figure 1 — LEO pass profile, {alt_km:.0f} km, peak elevation "
        f"{sat_pass.max_elevation_deg:.0f} deg\n"
        f"derived from {sat_pass.source} geometry; Earth rotation "
        f"{'not modelled' if sat_pass.source == 'circular' else 'modelled'}",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = FIGURES / "fig1_pass_profile.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--band", dest="bands", action="append",
                    choices=sorted(BANDS), help="repeatable; default is both")
    ap.add_argument("--source", choices=("circular", "tle"), default="circular")
    ap.add_argument("--tle", help="path to a two-line element set")
    ap.add_argument("--lat", type=float, default=39.3299, help="station latitude, deg")
    ap.add_argument("--lon", type=float, default=-76.6205, help="station longitude, deg")
    ap.add_argument("--station-alt", type=float, default=0.0, help="station height, m")
    ap.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE_M,
                    help="orbit altitude for the analytic model, m")
    ap.add_argument("--max-elevation", type=float, default=90.0,
                    help="peak elevation of the analytic pass, deg; 90 is worst case")
    ap.add_argument("--min-elevation", type=float, default=10.0,
                    help="horizon mask, deg")
    ap.add_argument("--dt", type=float, default=0.1, help="sample interval, s")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()
    args.bands = args.bands or sorted(BANDS)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        built = build(args)
    sat_pass, profiles = built["pass"], built["profiles"]

    print(f"pass source          {sat_pass.source}")
    print(f"altitude             {sat_pass.altitude_m / 1e3:.1f} km")
    print(f"orbital period       {orbital_period_s(sat_pass.altitude_m) / 60:.1f} min")
    print(f"orbital speed        {orbital_speed_ms(sat_pass.altitude_m) / 1e3:.3f} km/s")
    print(f"peak elevation       {sat_pass.max_elevation_deg:.2f} deg")
    print(f"visible duration     {sat_pass.duration_s:.1f} s "
          f"above {args.min_elevation:.0f} deg")
    print()

    rows = requirement_table(profiles)
    print(format_table(rows))
    print()

    for band, p in profiles.items():
        anchor = p.at_elevation(10.0)
        print(f"[{band}] at {anchor['elevation_deg']:.1f} deg elevation: "
              f"slant range {anchor['slant_range_m'] / 1e3:.0f} km, "
              f"one-way delay {anchor['delay_s'] * 1e3:.2f} ms, "
              f"round trip {2 * anchor['delay_s'] * 1e3:.2f} ms, "
              f"path loss {anchor['total_loss_db']:.1f} dB")

    stale = control_staleness_s(profiles[args.bands[0]])
    print()
    print("Near-RT control staleness from propagation alone, at "
          f"{stale['elevation_deg']:.1f} deg elevation:")
    print(f"  measurement is       {stale['measurement_age_s'] * 1e3:.2f} ms old on arrival")
    print(f"  action is            {stale['action_lateness_s'] * 1e3:.2f} ms late on landing")
    print(f"  total                {stale['total_staleness_s'] * 1e3:.2f} ms, which is "
          f"{stale['fraction_of_fastest_near_rt_loop']:.2f}x the fastest Near-RT loop period")

    written = save(sat_pass, profiles)
    summary = {
        "source": sat_pass.source,
        "altitude_m": sat_pass.altitude_m,
        "max_elevation_deg": sat_pass.max_elevation_deg,
        "min_elevation_deg": args.min_elevation,
        "requirements": [r.as_dict() for r in rows],
        "staleness": stale,
    }
    (DATA / "orbit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print()
    for w in caught:
        print(f"warning: {w.message}")
    for p in written:
        print(f"wrote {p.relative_to(REPO)}")
    print(f"wrote {(DATA / 'orbit_summary.json').relative_to(REPO)}")
    if not args.no_figure:
        print(f"wrote {figure_1(sat_pass, profiles).relative_to(REPO)}")


if __name__ == "__main__":
    main()
