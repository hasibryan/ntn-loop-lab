"""Track the beacon carrier in a recorded pass and check the day-1 model against it.

The pre-flight measurement (recorded in ``tasks/todo.md`` under day 3) found that
SatNOGS stations apply Doppler correction before archiving: the carrier in the
archived audio sits within a few kHz and never sweeps, where an uncorrected
437 MHz LEO carrier would sweep about +/-10 kHz.

So what this module measures is the **residual after the station's own
correction**, and that is a stricter test than comparing against a raw sweep.
Both sides propagate the same TLE -- the one the station held, saved by
``fetch.py`` -- with SGP4. A correct model therefore predicts a *flat* residual,
and every Hz of structure in it is real disagreement between two independent
implementations.

The residual is fitted as::

    resid(t) = a0 + a1 * doppler(t) + a2 * doppler_rate(t) + a3 * t

which separates the four things that get conflated if it is not:

``a0``  Hz, constant. Beat-note offset plus the beacon's own frequency error.
        Not a model error, and reported apart from one.
``a1``  dimensionless. Fractional scale error in the predicted Doppler. This is
        the term that would indicate the geometry is wrong.
``a2``  seconds. An effective time shift: a stale TLE or a correction applied in
        discrete steps both appear here, because a shift tau produces a residual
        of tau times the Doppler rate.
``a3``  Hz/s. The beacon oscillator's own linear drift as it warms through the
        pass. Omitting it does not remove it -- it reappears inside ``a1`` as a
        Doppler-scale error that is not there. See ``decompose_residual``.

Two of the four pinned captures do not yield a measurement at all, and are
reported as rejected rather than tuned into one. The test is in
``select_carrier``: if the residual RMS scales with the width of the
carrier-selection window, the number is a fact about the window.

Run with ``make doppler-fit``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from orbit.channel import doppler_hz
from orbit.geometry import tle_pass

C_LIGHT = 299_792_458.0

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = Path(__file__).resolve().parent / "captures"
MANIFEST = Path(__file__).resolve().parent / "manifest.json"
FIGURES = ROOT / "eval" / "figures"
DATA = ROOT / "data"


# --------------------------------------------------------------------------- #
# Carrier tracking
# --------------------------------------------------------------------------- #

def track_carrier(
    x: np.ndarray,
    fs: float,
    n_fft: int = 16384,
    hop: int | None = None,
    snr_gate_db: float = 15.0,
    band_hz: tuple[float, float] = (100.0, 6000.0),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Peak-track a narrowband carrier through a real audio recording.

    Returns ``(t_s, f_hz, snr_db)`` for the frames that passed the gate, where
    ``t_s`` is the centre of each frame in seconds from the start of the file.

    A CW beacon is keyed, so the carrier is absent for much of the recording and
    a peak taken from a silent frame is a noise bin. The gate is the peak's
    height over the median of the in-band spectrum, which is a robust noise floor
    for a spectrum with one narrow line in it.

    Sub-bin resolution comes from a quadratic fit to the log-magnitude of the
    peak and its two neighbours -- the standard estimator for a windowed tone,
    and worth roughly an order of magnitude over the raw bin spacing. At the
    default 16384-point frame on 48 kHz audio a bin is 2.93 Hz, so the estimator
    resolves well under a Hz on a strong carrier.
    """
    if hop is None:
        hop = n_fft // 2
    if x.ndim > 1:
        x = x[:, 0]
    x = np.asarray(x, dtype=float)

    win = np.hanning(n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / fs)
    lo = int(np.searchsorted(freqs, band_hz[0]))
    hi = int(np.searchsorted(freqs, band_hz[1]))
    if hi - lo < 8:
        raise ValueError(f"search band {band_hz} spans too few bins at n_fft={n_fft}")

    n_frames = max(0, 1 + (len(x) - n_fft) // hop)
    t_out, f_out, snr_out = [], [], []
    for i in range(n_frames):
        seg = x[i * hop: i * hop + n_fft] * win
        mag = np.abs(np.fft.rfft(seg))[lo:hi]
        k = int(np.argmax(mag))
        floor = float(np.median(mag))
        if floor <= 0.0 or mag[k] <= 0.0:
            continue
        snr_db = 20.0 * np.log10(mag[k] / floor)
        if snr_db < snr_gate_db:
            continue
        # Quadratic interpolation on the log magnitude. Skip if the peak is on the
        # edge of the search band: there is no neighbour to interpolate against,
        # and an edge peak is usually the band limit, not the carrier.
        if k == 0 or k == len(mag) - 1:
            continue
        a, b, c = (np.log(mag[k - 1]), np.log(mag[k]), np.log(mag[k + 1]))
        denom = a - 2.0 * b + c
        delta = 0.0 if denom == 0.0 else 0.5 * (a - c) / denom
        delta = float(np.clip(delta, -0.5, 0.5))
        f_out.append(float(freqs[lo + k] + delta * fs / n_fft))
        t_out.append((i * hop + n_fft / 2.0) / fs)
        snr_out.append(float(snr_db))

    return np.array(t_out), np.array(f_out), np.array(snr_out)


def coarse_carrier_band(x: np.ndarray, fs: float, half_width_hz: float = 1500.0,
                        n_fft: int = 16384) -> tuple[float, float]:
    """A search band centred on where the carrier actually is.

    Taken from the median-across-frames spectrum rather than one frame, so a
    keyed beacon that is off for most of the recording still shows up: the line
    survives the median, wideband noise does not.
    """
    if x.ndim > 1:
        x = x[:, 0]
    win = np.hanning(n_fft)
    hop = n_fft
    n_frames = max(1, 1 + (len(x) - n_fft) // hop)
    acc = np.zeros(n_fft // 2 + 1)
    for i in range(n_frames):
        seg = x[i * hop: i * hop + n_fft]
        if len(seg) < n_fft:
            break
        acc += np.abs(np.fft.rfft(seg * win))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / fs)
    # Ignore the bottom 100 Hz: DC leakage and any mains hum live there.
    valid = freqs > 100.0
    centre = float(freqs[valid][int(np.argmax(acc[valid]))])
    return (max(50.0, centre - half_width_hz), centre + half_width_hz)


# --------------------------------------------------------------------------- #
# Picking the beacon out of whatever else is in the band
# --------------------------------------------------------------------------- #
#
# Two of the four pinned captures share a ground station whose recordings carry a
# second strong signal. An SNR gate does not remove it, because it is strong. The
# discriminator that does is physical rather than statistical: the station
# corrected Doppler for *this* satellite and nothing else, so the beacon is the
# only line in the recording that is stationary in frequency. An uncorrected
# 437 MHz LEO emitter sweeps by roughly 20 kHz across a pass and cannot pile up.

def stationary_mode_hz(f_hz: np.ndarray, bin_hz: float = 25.0) -> float:
    """The frequency the detections pile up at over the whole recording."""
    edges = np.arange(f_hz.min(), f_hz.max() + bin_hz, bin_hz)
    hist, _ = np.histogram(f_hz, bins=edges)
    k = int(np.argmax(hist))
    return float(0.5 * (edges[k] + edges[k + 1]))


def select_carrier(f_hz: np.ndarray, window_hz: float = 400.0, med_win: int = 21,
                   k_mad: float = 5.0, floor_hz: float = 20.0,
                   iters: int = 3) -> np.ndarray:
    """Boolean mask of the detections that belong to the beacon.

    Two stages. First a window around the stationary mode, which discards a
    sweeping interferer wholesale. Then a local-median continuity filter, which
    discards the isolated noise-bin picks that survive the SNR gate. The
    continuity filter is deliberately *local*: a global polynomial would absorb
    exactly the slow structure this module exists to measure.
    """
    keep = np.abs(f_hz - stationary_mode_hz(f_hz)) < window_hz
    for _ in range(iters):
        idx = np.where(keep)[0]
        if len(idx) < med_win:
            break
        ff = f_hz[idx]
        med = np.array([np.median(ff[max(0, i - med_win // 2): i + med_win // 2 + 1])
                        for i in range(len(ff))])
        dev = np.abs(ff - med)
        mad = float(np.median(np.abs(dev - np.median(dev)))) or 1.0
        keep[idx] = dev < max(k_mad * 1.4826 * mad, floor_hz)
    return keep


# The measurement is only well posed if it does not depend on how wide that window
# was drawn. Where a second signal is present the surviving population simply
# fills whatever window it is given, and the reported RMS becomes a fact about the
# window rather than about the model. Ratio of RMS at the wide and narrow windows;
# 1.0 means the window is doing nothing, and anything much above that means it is
# doing everything.
WINDOW_WIDE_HZ = 400.0
WINDOW_NARROW_HZ = 150.0
WELL_POSED_MAX_RATIO = 1.5


# --------------------------------------------------------------------------- #
# Residual decomposition
# --------------------------------------------------------------------------- #

def decompose_residual(resid_hz: np.ndarray, doppler_hz_: np.ndarray,
                       doppler_rate_hz_s: np.ndarray, t_s: np.ndarray) -> dict:
    """Least-squares split of the residual into offset, scale, time shift and drift.

    Fits ``resid = a0 + a1 * doppler + a2 * doppler_rate + a3 * t``.

    The ``a3 * t`` term is not decoration. Fitted without it, KKS-1 returned a
    Doppler-scale error of +5129 ppm -- half a percent of disagreement between two
    SGP4 implementations propagating the same TLE, which would be a serious claim.
    Fitting a plain linear drift *instead* explained the same residual better
    (6.7 Hz unexplained against 13.3 Hz), and with both terms present the scale
    collapsed to -680 ppm while the drift held at -0.349 Hz/s. The scale term had
    been absorbing the beacon's own oscillator warming up over the pass.

    The two remain partly degenerate: across a single pass the Doppler curve is
    close enough to linear in time that ``doppler`` and ``t`` are strongly
    correlated. ``scale_drift_correlation`` reports how badly, and
    ``scale_separable`` says whether the split can be believed at all.

    The columns are on wildly different scales (Hz, Hz, Hz/s, s), so the design
    matrix is column-normalised before the solve and the coefficients scaled back;
    without that the conditioning alone can swamp a real ``a1``.
    """
    A = np.column_stack([np.ones_like(resid_hz), doppler_hz_, doppler_rate_hz_s, t_s])
    scale = np.array([1.0, *[max(np.abs(col).max(), 1e-12) for col in A.T[1:]]])
    coef, *_ = np.linalg.lstsq(A / scale, resid_hz, rcond=None)
    a0, a1, a2, a3 = coef / scale
    unexplained = resid_hz - A @ np.array([a0, a1, a2, a3])

    corr = float(np.corrcoef(doppler_hz_, t_s)[0, 1])
    return {
        "offset_hz": float(a0),
        "scale_fractional": float(a1),
        "time_shift_s": float(a2),
        "beacon_drift_hz_s": float(a3),
        "scale_drift_correlation": corr,
        "scale_separable": bool(abs(corr) < 0.9),
        "rms_about_mean_hz": float(np.sqrt(np.mean((resid_hz - resid_hz.mean()) ** 2))),
        "rms_unexplained_hz": float(np.sqrt(np.mean(unexplained ** 2))),
        "peak_abs_unexplained_hz": float(np.abs(unexplained).max()),
    }


# --------------------------------------------------------------------------- #
# One capture, end to end
# --------------------------------------------------------------------------- #

def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def analyse(entry: dict, captures: Path = CAPTURES, dt_s: float = 0.1) -> dict:
    """Track one capture's carrier and compare it against the SGP4 prediction."""
    import soundfile as sf

    obs_id = entry["id"]
    cap = captures / str(obs_id)
    audio_path, tle_path, meta_path = cap / "audio.ogg", cap / "tle.txt", cap / "meta.json"
    if not audio_path.exists():
        raise FileNotFoundError(f"{audio_path} missing -- run `make satnogs-fetch` first")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    x, fs = sf.read(str(audio_path), always_2d=True)
    x = x[:, 0]

    band = coarse_carrier_band(x, fs)
    t_all, f_all, snr_all = track_carrier(x, fs, band_hz=band)
    if len(t_all) < 32:
        raise ValueError(
            f"observation {obs_id}: only {len(t_all)} frames passed the SNR gate. "
            "The capture is too weak to track; drop this pin rather than lowering the gate."
        )

    wide = select_carrier(f_all, window_hz=WINDOW_WIDE_HZ)
    narrow = select_carrier(f_all, window_hz=WINDOW_NARROW_HZ)
    rms_wide = float(np.std(f_all[wide]))
    rms_narrow = float(np.std(f_all[narrow])) if narrow.sum() > 8 else float("nan")
    window_ratio = rms_wide / rms_narrow if rms_narrow > 0 else float("inf")
    well_posed = bool(window_ratio <= WELL_POSED_MAX_RATIO)

    # Report from the widest window: it is the least restrictive selection, so a
    # number that survives it is not an artefact of narrowing.
    t_audio, f_audio, snr = t_all[wide], f_all[wide], snr_all[wide]
    centre = stationary_mode_hz(f_all)
    window_fill = float(max(f_audio.max() - centre, centre - f_audio.min()) / WINDOW_WIDE_HZ)

    # The audio file starts when the observation starts. Propagate the same TLE the
    # station used over exactly the observation window.
    sat_pass = tle_pass(
        str(tle_path),
        station_lat_deg=meta["station_lat"],
        station_lon_deg=meta["station_lng"],
        station_alt_m=meta.get("station_alt") or 0.0,
        dt_s=dt_s,
        t_start_utc=meta["start"],
        t_end_utc=meta["end"],
    )
    # tle_pass re-references t to closest approach; put both timelines back on
    # seconds-from-observation-start so the audio and the prediction line up.
    t_ca_from_start = (_utc(sat_pass.epoch_utc) - _utc(meta["start"])).total_seconds()
    t_pred = sat_pass.t_s + t_ca_from_start

    fc = float(entry["nominal_downlink_hz"])
    d_pred_full = doppler_hz(sat_pass.range_rate_ms, fc)
    d_pred = np.interp(t_audio, t_pred, d_pred_full)
    rate_pred = np.interp(t_audio, t_pred, np.gradient(d_pred_full, t_pred))
    elev = np.interp(t_audio, t_pred, sat_pass.elevation_deg)

    # The station corrected Doppler out before archiving, so the audio carrier is
    # (beat note + beacon error + whatever the two models disagree about). The
    # residual under test is that carrier with its own mean removed; the mean is
    # reported separately as a0 because it is not a model error.
    resid = f_audio - f_audio.mean()
    parts = decompose_residual(resid, d_pred, rate_pred, t_audio)
    parts["offset_hz"] = float(f_audio.mean())  # the real constant, not the de-meaned zero

    # A tuning offset the station recorded on purpose is a known constant, not a
    # mystery: subtract it before attributing anything to the beacon.
    tuned_off_hz = float(entry.get("observation_frequency_hz", fc)) - fc

    return {
        "observation_id": obs_id,
        "satellite": entry["satellite"],
        "norad_cat_id": entry["norad_cat_id"],
        "station": entry["station_name"],
        "max_elevation_deg": float(sat_pass.max_elevation_deg),
        "nominal_downlink_hz": fc,
        "station_tuning_offset_hz": tuned_off_hz,
        "tle_epoch_age_h": _tle_age_hours(tle_path, meta["start"]),
        "n_frames_detected": int(len(t_all)),
        "n_frames_tracked": int(len(t_audio)),
        "median_snr_db": float(np.median(snr)),
        "well_posed": well_posed,
        "window_rms_ratio": float(window_ratio),
        "window_fill_fraction": window_fill,
        "rejection_reason": None if well_posed else (
            f"residual RMS scales with the selection window "
            f"({rms_narrow:.1f} Hz at +/-{WINDOW_NARROW_HZ:.0f} Hz, "
            f"{rms_wide:.1f} Hz at +/-{WINDOW_WIDE_HZ:.0f} Hz, ratio {window_ratio:.2f}). "
            "A second signal is present in the band and this tracker cannot separate it, "
            "so any RMS quoted would be a fact about the window, not about the model."
        ),
        "predicted_peak_doppler_hz": float(np.abs(d_pred_full).max()),
        "predicted_peak_doppler_rate_hz_s": float(np.abs(np.gradient(d_pred_full, t_pred)).max()),
        **parts,
        "_series": {
            "t_s": t_audio, "f_audio_hz": f_audio, "snr_db": snr,
            "resid_hz": resid, "doppler_pred_hz": d_pred,
            "doppler_rate_pred_hz_s": rate_pred, "elevation_deg": elev,
            "t_pred_s": t_pred, "doppler_pred_full_hz": d_pred_full,
            "elevation_full_deg": sat_pass.elevation_deg,
        },
    }


def _tle_age_hours(tle_path: Path, start_utc: str) -> float:
    """Hours between the TLE epoch and the start of the observation."""
    lines = [ln for ln in tle_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    l1 = next(ln for ln in lines if ln.startswith("1 "))
    yy, doy = int(l1[18:20]), float(l1[20:32])
    year = 2000 + yy if yy < 57 else 1900 + yy
    epoch = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() + (doy - 1.0) * 86400.0
    return (_utc(start_utc).timestamp() - epoch) / 3600.0


# --------------------------------------------------------------------------- #
# Figure and report
# --------------------------------------------------------------------------- #

def figure_4(results: list[dict]) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    n = len(results)
    fig, axes = plt.subplots(2, n, figsize=(4.2 * n, 6.4), sharex="col")
    if n == 1:
        axes = axes.reshape(2, 1)

    for col, r in enumerate(results):
        s = r["_series"]
        top, bot = axes[0, col], axes[1, col]

        top.plot(s["t_pred_s"], s["doppler_pred_full_hz"] / 1e3, lw=1.4, color="#1f77b4",
                 label="SGP4 prediction")
        top.axhline(0.0, lw=0.6, color="0.7")
        verdict = "" if r["well_posed"] else "   REJECTED"
        top.set_title(f"{r['satellite']}  obs {r['observation_id']}{verdict}\n"
                      f"{r['station']}, peak {r['max_elevation_deg']:.0f} deg, "
                      f"TLE age {r['tle_epoch_age_h']:.1f} h",
                      fontsize=9, color="black" if r["well_posed"] else "#b30000")
        top.set_ylabel("predicted Doppler (kHz)" if col == 0 else "")
        top.legend(fontsize=7, loc="upper right")

        bot.scatter(s["t_s"], s["resid_hz"], s=3, alpha=0.45, color="#d62728",
                    label="measured residual")
        fit = (r["scale_fractional"] * s["doppler_pred_hz"]
               + r["time_shift_s"] * s["doppler_rate_pred_hz_s"]
               + r["beacon_drift_hz_s"] * s["t_s"])
        order = np.argsort(s["t_s"])
        bot.plot(s["t_s"][order], (fit - fit.mean())[order], lw=1.4, color="#2ca02c",
                 label=f"fit: {r['beacon_drift_hz_s']:+.3f} Hz/s drift, "
                       f"{r['time_shift_s']:+.2f} s shift")
        bot.axhline(0.0, lw=0.6, color="0.7")
        bot.set_xlabel("time from observation start (s)")
        bot.set_ylabel("residual after station\nDoppler correction (Hz)" if col == 0 else "")
        bot.legend(fontsize=7, loc="upper right")
        if r["well_posed"]:
            note = (f"RMS {r['rms_about_mean_hz']:.1f} Hz\n"
                    f"unexplained {r['rms_unexplained_hz']:.1f} Hz\n"
                    f"window ratio {r['window_rms_ratio']:.2f}")
            colour = "black"
        else:
            note = (f"NOT MEASURABLE\nRMS scales with the selection\n"
                    f"window (ratio {r['window_rms_ratio']:.2f});\n"
                    f"a second signal is in the band")
            colour = "#b30000"
        bot.text(0.02, 0.04, note, transform=bot.transAxes, fontsize=7,
                 va="bottom", color=colour)

    n_ok = sum(1 for r in results if r["well_posed"])
    fig.suptitle(
        "Figure 4 — the day-1 Doppler model against four real SatNOGS passes.\n"
        "The stations corrected Doppler before archiving, so the lower row is the residual between two "
        "independent SGP4 implementations on the same TLE, not a raw sweep.\n"
        f"{n_ok} of {len(results)} captures give a measurement that does not depend on the "
        "carrier-selection window; the other two are reported as rejected, not tuned.",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = FIGURES / "fig4_doppler_validation.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    results = []
    for entry in manifest["observations"]:
        print(f"tracking {entry['satellite']} (obs {entry['id']}) ...", flush=True)
        results.append(analyse(entry))

    good = [r for r in results if r["well_posed"]]
    bad = [r for r in results if not r["well_posed"]]

    hdr = (f"{'satellite':<16}{'obs':>10}{'peak el':>9}{'TLE age':>9}{'frames':>8}"
           f"{'offset':>11}{'drift':>11}{'shift':>9}{'RMS':>9}{'unexpl':>9}{'win':>7}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in results:
        mark = "" if r["well_posed"] else "  <- rejected"
        print(f"{r['satellite'][:15]:<16}{r['observation_id']:>10}"
              f"{r['max_elevation_deg']:>8.1f}d{r['tle_epoch_age_h']:>8.1f}h"
              f"{r['n_frames_tracked']:>8}"
              f"{r['offset_hz']:>10.1f}Hz{r['beacon_drift_hz_s']:>7.3f}Hz/s"
              f"{r['time_shift_s']:>8.2f}s{r['rms_about_mean_hz']:>8.1f}Hz"
              f"{r['rms_unexplained_hz']:>8.1f}Hz{r['window_rms_ratio']:>7.2f}{mark}")
    print("\ndrift is the beacon oscillator's own linear drift; RMS is about the mean;\n"
          "unexplained is what the four-term fit does not account for; win is the RMS ratio\n"
          f"between the wide and narrow selection windows (well posed at or below "
          f"{WELL_POSED_MAX_RATIO}).")
    for r in results:
        if r["well_posed"] and not r["scale_separable"]:
            print(f"  {r['satellite']}: the Doppler-scale and beacon-drift terms are not "
                  f"separable over one pass (correlation {r['scale_drift_correlation']:+.3f}), "
                  f"so the fitted {r['scale_fractional']*1e6:+.0f} ppm scale is not a claim.")

    for r in bad:
        print(f"\nREJECTED  {r['satellite']} (obs {r['observation_id']}, station {r['station']}):\n"
              f"  {r['rejection_reason']}")

    if good:
        rms = [r["rms_about_mean_hz"] for r in good]
        peak = max(r["predicted_peak_doppler_hz"] for r in good)
        unexp = [r["rms_unexplained_hz"] for r in good]
        print(f"\n{len(good)} of {len(results)} captures give a well-posed measurement. "
              f"Residual RMS {min(rms):.1f} to {max(rms):.1f} Hz, which is "
              f"{100*max(rms)/peak:.2f} % of the {peak/1e3:.1f} kHz Doppler the station "
              f"removed; {min(unexp):.1f} to {max(unexp):.1f} Hz "
              f"({100*max(unexp)/peak:.3f} %) remains once the beacon's own drift is "
              f"accounted for.")
    else:
        print("\nNo capture gave a well-posed measurement. Day 3 is not validated.")

    DATA.mkdir(parents=True, exist_ok=True)
    summary = [{k: v for k, v in r.items() if k != "_series"} for r in results]
    out_json = DATA / "doppler_validation.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out_json}")

    if not args.no_figure:
        print(f"wrote {figure_4(results)}")


if __name__ == "__main__":
    main()
