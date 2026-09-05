"""Pull the pinned SatNOGS observations.

Day 3 validates the day-1 model against data this lab did not generate. That is
only worth anything if the download is reproducible, so nothing here searches:
``manifest.json`` names exact observation IDs and this module fetches those and
no others.

Three things land in ``satnogs/captures/<id>/``:

``meta.json``  the API record verbatim, unmodified. Provenance.
``tle.txt``    the TLE the *station* held at capture time, taken off that same
               record. Never a fresher one fetched later -- comparing a
               measurement against a TLE the receiver never saw measures the
               wrong thing.
``audio.ogg``  the demodulated audio the station archived.

Run with ``make satnogs-fetch``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

API = "https://network.satnogs.org/api/observations/{id}/?format=json"
UA = "ntn-loop-lab/0.1 (+https://github.com/hasibryan/ntn-loop-lab)"
CAPTURES = Path(__file__).resolve().parent / "captures"


def observation_record(obs_id: int, timeout: float = 45.0) -> dict:
    """The SatNOGS Network record for one observation."""
    r = requests.get(API.format(id=obs_id), headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def download(url: str, dest: Path, timeout: float = 180.0) -> int:
    """Stream a URL to a file. Returns bytes written."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    written = 0
    with requests.get(url, headers={"User-Agent": UA}, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for block in r.iter_content(chunk_size=1 << 16):
                fh.write(block)
                written += len(block)
    tmp.replace(dest)
    return written


def fetch_one(entry: dict, out_root: Path = CAPTURES, force: bool = False) -> Path:
    """Fetch one pinned observation. Idempotent unless ``force``."""
    obs_id = entry["id"]
    out = out_root / str(obs_id)
    out.mkdir(parents=True, exist_ok=True)

    meta_path, tle_path, audio_path = out / "meta.json", out / "tle.txt", out / "audio.ogg"

    if meta_path.exists() and not force:
        rec = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        rec = observation_record(obs_id)
        meta_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    # The manifest was written by hand from the API; if the record has since been
    # re-vetted or re-tagged, the run must not silently proceed on a different pass.
    for field, key in (("norad_cat_id", "norad_cat_id"), ("start", "start")):
        if str(rec.get(key)) != str(entry[field]):
            raise ValueError(
                f"observation {obs_id}: manifest says {field}={entry[field]!r} "
                f"but the API record says {rec.get(key)!r}. The pin is stale."
            )

    if not rec.get("tle1") or not rec.get("tle2"):
        raise ValueError(f"observation {obs_id} carries no TLE; it cannot be validated against")
    tle_path.write_text(
        "\n".join([rec.get("tle0") or entry["satellite"], rec["tle1"], rec["tle2"]]) + "\n",
        encoding="utf-8",
    )

    url = rec.get("payload") or rec.get("archive_url")
    if not url:
        raise ValueError(
            f"observation {obs_id} has neither payload nor archive_url; "
            "the audio was never published and this pin must be replaced"
        )
    if audio_path.exists() and not force:
        size = audio_path.stat().st_size
        print(f"  {obs_id}  audio.ogg already present ({size:,} bytes)")
    else:
        size = download(url, audio_path)
        print(f"  {obs_id}  audio.ogg {size:,} bytes from {url.split('/')[2]}")

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(Path(__file__).resolve().parent / "manifest.json"))
    ap.add_argument("--force", action="store_true", help="re-download even if the file is present")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    entries = manifest["observations"]
    if not entries:
        raise SystemExit("manifest pins no observations; day 3 has nothing to fetch")

    print(f"fetching {len(entries)} pinned observations into {CAPTURES}")
    for entry in entries:
        print(f"- {entry['satellite']} (NORAD {entry['norad_cat_id']}, "
              f"{entry['mode']}, peak {entry['max_elevation_deg']:.0f} deg)")
        fetch_one(entry, force=args.force)
    print("done")


if __name__ == "__main__":
    main()
