"""Download the public datasets into ml/data/raw/ (stdlib only).

    python ml/download_datasets.py           # UCI Occupancy + NAB (~4 MB)
    python ml/download_datasets.py --lbnl    # also LBNL fan-coil FDD data (~530 MB)

Sources and licences (verified 2026-10-24):
  UCI Occupancy Detection  CC BY 4.0  https://archive.ics.uci.edu/dataset/357/occupancy+detection
  Numenta Anomaly Benchmark  MIT      https://github.com/numenta/NAB
  LBNL FDD (fan coil unit)   CC BY 4.0  https://catalog.data.gov/dataset/lbnl-fault-detection-and-diagnostics-datasets
  ASHRAE GEP III (Kaggle)  competition rules, needs a Kaggle account -> manual, see README
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).parent / "data" / "raw"

NAB = "https://raw.githubusercontent.com/numenta/NAB/master/"
FILES = {
    # target path (relative to RAW) -> URL
    "uci_occupancy/occupancy.zip":
        "https://archive.ics.uci.edu/static/public/357/occupancy+detection.zip",
    # Real machine-temperature series that ends in a known failure (tests Layer 2 + forecast)
    "nab/machine_temperature_system_failure.csv":
        NAB + "data/realKnownCause/machine_temperature_system_failure.csv",
    "nab/combined_windows.json": NAB + "labels/combined_windows.json",  # anomaly windows
}
LBNL = {
    "lbnl_fcu/LBNL_FDD_Data_Sets_FCU.zip":
        "https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_FCU/LBNL_FDD_Data_Sets_FCU.zip",
}


def fetch(rel, url):
    dest = RAW / rel
    if dest.exists():
        print(f"skip   {rel} (already there)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"get    {rel}")
    tmp = dest.with_suffix(dest.suffix + ".part")  # no half-files if interrupted
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    return dest


def main():
    files = FILES | (LBNL if "--lbnl" in sys.argv else {})
    for rel, url in files.items():
        path = fetch(rel, url)
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as z:
                z.extractall(path.parent)
            print(f"unzip  {rel}")
    print("\nASHRAE GEP III: download manually from Kaggle (see README).")


if __name__ == "__main__":
    main()
