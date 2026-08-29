"""Day 2 entry point: array pattern, quantisation cost, SINR over the pass, and the
beam-dwell requirement that day 1 could not produce on its own.

    make array
    make array BAND=ka
    python -m antenna.beams --nx 8 --ny 8 --bits 6 --band s

Consumes ``data/ntn_channel_<band>.npz`` from day 1. Writes ``data/array_<band>.npz``
for day 4's shim and day 9's environment, and draws Figures 2 and 3.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from orbit.channel import channel_profile
from orbit.constants import BANDS, C, DEFAULT_ALTITUDE_M
from orbit.geometry import circular_pass
from orbit.requirements import tier_for
from .interference import (LinkScenario, beam_dwell_s, beam_gains_over_pass,
                           elements_per_side_for_dwell, line_of_sight_rate_deg_s,
                           sinr_from_gains)
from .ura import (URA, beam_pull_deg, combine_hybrid, cut_pattern, hybrid_weights,
                  pattern_metrics)

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
FIGURES = REPO / "eval" / "figures"

MODES = ("fixed", "ideal", "quantised")


def figure_2(array: URA, bits: int, n_rf: int, steer_deg: float, band: str) -> Path:
    """Pattern cuts: boresight, steered, and steered through quantised shifters."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(10.0, 4.2))

    cases = [
        ("boresight, ideal", array.conjugate_weights(0.0, 0.0), "k", "-"),
        (f"steered {steer_deg:.0f} deg, ideal",
         array.conjugate_weights(steer_deg, 0.0), "tab:blue", "-"),
    ]
    a, d = hybrid_weights(array, steer_deg, 0.0, n_rf=n_rf, bits=bits)
    cases.append((f"steered {steer_deg:.0f} deg, {bits}-bit hybrid {array.n_elements}x{n_rf}",
                  combine_hybrid(a, d), "tab:red", "--"))

    rows = []
    for label, w, col, ls in cases:
        th, g = cut_pattern(array, w)
        m = pattern_metrics(th, g)
        rows.append((label, m))
        ax[0].plot(th, g, ls, color=col, lw=1.2,
                   label=f"{label}\nHPBW {m['hpbw_deg']:.1f} deg, SLL {m['first_sll_db']:.1f} dB")
        ax[1].plot(th, g, ls, color=col, lw=1.2)

    ax[0].set_xlim(-90, 90)
    ax[0].set_ylim(-30, max(r[1]["peak_gain_dbi"] for r in rows) + 3)
    ax[0].set_xlabel("angle off boresight (deg)")
    ax[0].set_ylabel("gain (dBi)")
    ax[0].legend(fontsize=7, loc="lower center")
    ax[0].grid(alpha=0.3)

    ax[1].set_xlim(steer_deg - 25, steer_deg + 25)
    ax[1].set_ylim(-15, max(r[1]["peak_gain_dbi"] for r in rows) + 3)
    ax[1].set_xlabel("angle off boresight (deg)")
    ax[1].set_title("main lobe, steered", fontsize=9)
    ax[1].grid(alpha=0.3)

    fig.suptitle(
        f"Figure 2 — {BANDS[band]['label']}, {array.nx}x{array.ny} URA at "
        f"{array.spacing:g} wavelength spacing\nTR 38.901 element pattern applied "
        f"rotationally symmetric, which is a modelling choice, not the standard",
        fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    # The configuration goes in the filename. A fixed name means a Ka run silently
    # overwrites the S-band figure, and the caption stops matching the picture.
    out = FIGURES / f"fig2_pattern_{band}_{array.nx}x{array.ny}.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def figure_3(results: dict, band: str, dwell: dict, cfg: str) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(3, 1, figsize=(7.2, 7.6), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1, 2]})
    styles = {"fixed": ("k", ":"), "ideal": ("tab:blue", "-"), "quantised": ("tab:red", "--")}

    any_res = next(iter(results.values()))
    for mode, r in results.items():
        col, ls = styles[mode]
        ax[0].plot(r.t_s, r.sinr_db, ls, color=col, lw=1.2,
                   label=f"{mode} (median {np.median(r.sinr_db):.1f} dB)")
    ax[0].set_ylabel("SINR (dB)")
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=0.3)

    ax[1].plot(any_res.t_s, any_res.n_visible_interferers, color="k", lw=1.0)
    ax[1].set_ylabel("co-channel\nneighbours visible")
    ax[1].grid(alpha=0.3)

    rate = dwell["rate_series"]
    ax[2].plot(any_res.t_s, rate, color="k", lw=1.2)
    ax[2].set_ylabel("line-of-sight rate\n(deg/s)")
    ax[2].set_xlabel("time from closest approach (s)")
    ax[2].grid(alpha=0.3)
    ax[2].axhline(dwell["peak_los_rate_deg_s"], color="tab:red", ls="--", lw=0.8)
    ax[2].annotate(f"peak {dwell['peak_los_rate_deg_s']:.2f} deg/s -> "
                   f"minimum dwell {dwell['min_dwell_s']:.1f} s",
                   xy=(0, dwell["peak_los_rate_deg_s"]), fontsize=8,
                   xytext=(6, -12), textcoords="offset points", color="tab:red")

    fig.suptitle(
        f"Figure 3 — {BANDS[band]['label']}, {cfg} array: SINR over one pass\n"
        f"co-channel interference from the same ground track at the constellation's\n"
        f"in-plane spacing; EIRP and system temperature are scenario parameters",
        fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    out = FIGURES / f"fig3_sinr_{band}_{cfg}.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--band", default="s", choices=sorted(BANDS))
    ap.add_argument("--nx", type=int, default=8)
    ap.add_argument("--ny", type=int, default=8)
    ap.add_argument("--spacing", type=float, default=0.5, help="wavelengths")
    ap.add_argument("--bits", type=int, default=6, help="analog phase shifter bits")
    ap.add_argument("--n-rf", type=int, default=4, help="RF chains in the hybrid split")
    ap.add_argument("--aperture-m", type=float, default=None,
                    help="size the array to a physical aperture instead of a fixed "
                         "element count. Comparing S and Ka at the same element count "
                         "silently compares a 52 cm panel with a 4 cm one; matching "
                         "aperture is the comparison that means something.")
    ap.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE_M)
    ap.add_argument("--min-elevation", type=float, default=10.0)
    ap.add_argument("--dt", type=float, default=0.5,
                    help="sample interval, s; 0.5 is enough for SINR and keeps the "
                         "quantised sweep under a minute")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    wavelength_m = C / BANDS[args.band]["fc_hz"]
    if args.aperture_m is not None:
        n_side = max(2, int(round(args.aperture_m / (args.spacing * wavelength_m))))
        args.nx = args.ny = n_side
    array = URA(nx=args.nx, ny=args.ny, spacing=args.spacing)
    aperture_m = array.nx * args.spacing * wavelength_m
    scenario = LinkScenario(min_elevation_deg=args.min_elevation,
                            phase_bits=args.bits, n_rf_chains=args.n_rf)

    sat_pass = circular_pass(args.altitude, dt_s=args.dt).visible(args.min_elevation)
    profile = channel_profile(sat_pass, BANDS[args.band]["fc_hz"])

    # Beamwidth first: the dwell requirement depends on it.
    th, g = cut_pattern(array, array.conjugate_weights(0.0, 0.0))
    boresight = pattern_metrics(th, g)
    dwell = beam_dwell_s(sat_pass, boresight["hpbw_deg"])
    dwell["rate_series"] = line_of_sight_rate_deg_s(sat_pass)

    print(f"band                 {BANDS[args.band]['label']}, "
          f"wavelength {wavelength_m * 100:.2f} cm")
    print(f"array                {array.nx}x{array.ny} URA, {array.n_elements} elements, "
          f"{array.spacing:g} wavelength spacing")
    print(f"physical aperture    {aperture_m * 100:.1f} x {aperture_m * 100:.1f} cm")
    print(f"boresight peak gain  {boresight['peak_gain_dbi']:.2f} dBi")
    print(f"boresight HPBW       {boresight['hpbw_deg']:.2f} deg  (measured off the pattern)")
    print(f"first sidelobe       {boresight['first_sll_db']:.2f} dB")
    print()

    # Gains once per mode; the budget and its sensitivity sweep are arithmetic on top.
    gains = {mode: beam_gains_over_pass(sat_pass, array, scenario, mode=mode)
             for mode in MODES}
    results = {mode: sinr_from_gains(g, profile, scenario) for mode, g in gains.items()}

    # Scan performance at a moderate steering angle. Metrics quoted at the pass's
    # worst angle, 80 degrees off boresight, are misleading: the element pattern
    # pulls the true peak well inside the commanded direction, so "first sidelobe"
    # there is measuring beam pulling rather than array sidelobe level.
    scan_deg = 60.0
    th_s, g_s = cut_pattern(array, array.conjugate_weights(scan_deg, 0.0))
    scan = pattern_metrics(th_s, g_s)
    a_q, d_q = hybrid_weights(array, scan_deg, 0.0, n_rf=args.n_rf, bits=args.bits)
    th_q, g_q = cut_pattern(array, combine_hybrid(a_q, d_q))
    scan_q = pattern_metrics(th_q, g_q)

    print(f"steered to {scan_deg:.0f} deg off boresight")
    print(f"  ideal        peak {scan['peak_gain_dbi']:.2f} dBi, "
          f"HPBW {scan['hpbw_deg']:.2f} deg, SLL {scan['first_sll_db']:.2f} dB")
    print(f"  {args.bits}-bit hybrid peak {scan_q['peak_gain_dbi']:.2f} dBi, "
          f"HPBW {scan_q['hpbw_deg']:.2f} deg, SLL {scan_q['first_sll_db']:.2f} dB")
    print(f"  scan loss    {boresight['peak_gain_dbi'] - scan['peak_gain_dbi']:.2f} dB "
          f"against boresight")
    print(f"  quantisation {scan['peak_gain_dbi'] - scan_q['peak_gain_dbi']:.2f} dB "
          f"of peak gain, {scan_q['first_sll_db'] - scan['first_sll_db']:+.2f} dB of "
          f"sidelobe level")
    print()

    # Open-loop pointing error. The element pattern is falling while the array factor
    # is rising, so the composite lobe lands short of the commanded angle. Near the
    # horizon the shortfall exceeds a whole beamwidth, which is the day-2 result that
    # gives the day-9 agent something real to correct.
    pull_angles = (15.0, 30.0, 45.0, 60.0, 75.0, 80.0)
    pulls = {a_: beam_pull_deg(array, a_) for a_ in pull_angles}
    print(f"open-loop pointing error, boresight HPBW {boresight['hpbw_deg']:.2f} deg")
    print(f"  {'commanded':>10}  {'lands at':>9}  {'error':>7}")
    for a_, pull in pulls.items():
        flag = "  <- exceeds a beamwidth" if pull > boresight["hpbw_deg"] else ""
        print(f"  {a_:>7.0f} deg  {a_ - pull:>6.2f} deg  {pull:>4.2f} deg{flag}")
    print()

    print(f"{'mode':<11} {'median SINR':>12} {'5th pct':>10} {'95th pct':>10}")
    print("-" * 46)
    for mode, r in results.items():
        print(f"{mode:<11} {np.median(r.sinr_db):>9.2f} dB "
              f"{np.percentile(r.sinr_db, 5):>7.2f} dB "
              f"{np.percentile(r.sinr_db, 95):>7.2f} dB")

    q_loss = float(np.median(results["ideal"].sinr_db) - np.median(results["quantised"].sinr_db))
    print()
    print(f"{args.bits}-bit hybrid {array.n_elements}x{args.n_rf} costs "
          f"{q_loss:.2f} dB of median SINR against ideal full-digital steering")

    # The interference result rests on one unmeasured parameter, so state how much it
    # rests on it rather than quoting a single number.
    print()
    print("sensitivity to satellite-side beam discrimination "
          "(a scenario parameter, not a measurement)")
    print(f"  {'discrimination':>14}  {'median SINR':>11}  {'5th pct':>9}")
    for disc in (10.0, 20.0, 25.0, 30.0, 40.0):
        sc = replace(scenario, sat_beam_discrimination_db=disc)
        r = sinr_from_gains(gains["ideal"], profile, sc)
        print(f"  {disc:>11.0f} dB  {np.median(r.sinr_db):>8.2f} dB "
              f"{np.percentile(r.sinr_db, 5):>6.2f} dB")

    print()
    print("beam-tracking requirement")
    print(f"  peak line-of-sight rate   {dwell['peak_los_rate_deg_s']:.3f} deg/s")
    print(f"  minimum beam dwell        {dwell['min_dwell_s']:.2f} s  "
          f"-> {tier_for(dwell['min_dwell_s'])}")
    n_needed = elements_per_side_for_dwell(sat_pass, 1.0, args.spacing)
    print(f"  a dwell of 1 s would need {n_needed:.0f}x{n_needed:.0f} elements "
          f"({n_needed**2:.0f} total)")

    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / f"array_{args.band}.npz"
    np.savez_compressed(
        out,
        t_s=sat_pass.t_s,
        elevation_deg=sat_pass.elevation_deg,
        **{f"sinr_db_{m}": results[m].sinr_db for m in MODES},
        **{f"carrier_dbw_{m}": results[m].carrier_dbw for m in MODES},
        n_visible_interferers=results["ideal"].n_visible_interferers,
        noise_dbw=results["ideal"].noise_dbw,
        los_rate_deg_s=dwell["rate_series"],
        hpbw_deg=boresight["hpbw_deg"],
        fc_hz=profile.fc_hz,
    )

    summary = {
        "band": args.band,
        "array": {"nx": args.nx, "ny": args.ny, "spacing_wavelengths": args.spacing,
                  "phase_bits": args.bits, "n_rf_chains": args.n_rf,
                  "wavelength_m": wavelength_m, "aperture_m": aperture_m},
        "boresight": boresight,
        "steered": {m: results[m].metrics for m in MODES},
        "median_sinr_db": {m: float(np.median(results[m].sinr_db)) for m in MODES},
        "p5_sinr_db": {m: float(np.percentile(results[m].sinr_db, 5)) for m in MODES},
        "quantisation_cost_db": q_loss,
        "open_loop_pointing_error_deg": {str(k): v for k, v in pulls.items()},
        "beam_dwell": {k: v for k, v in dwell.items() if k != "rate_series"},
        "beam_dwell_tier": tier_for(dwell["min_dwell_s"]),
        "elements_per_side_for_1s_dwell": n_needed,
        "scenario": {"eirp_dbw": scenario.eirp_dbw, "t_system_k": scenario.t_system_k,
                     "bandwidth_hz": scenario.bandwidth_hz,
                     "inplane_spacing_s": scenario.inplane_spacing_s},
    }
    (DATA / f"array_summary_{args.band}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    print()
    print(f"wrote {out.relative_to(REPO)}")
    print(f"wrote {(DATA / f'array_summary_{args.band}.json').relative_to(REPO)}")
    if not args.no_figure:
        steer = results["ideal"].metrics["steered_to_deg"]
        print(f"wrote {figure_2(array, args.bits, args.n_rf, steer, args.band).relative_to(REPO)}")
        print(f"wrote {figure_3(results, args.band, dwell, f'{array.nx}x{array.ny}').relative_to(REPO)}")


if __name__ == "__main__":
    main()
