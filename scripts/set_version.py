"""Atomic version bump before tagging releases; invoked by GH Actions."""

from pathlib import Path
import json
import re
import sys

version = sys.argv[1] if len(sys.argv) == 2 else ""
if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:rc|beta|alpha)\.[0-9]+)?", version):
    raise SystemExit(f"Invalid semantic version: {version!r}")
root = Path(__file__).resolve().parents[1]
manifest = root / "custom_components/gismeteo_ha/manifest.json"
data = json.loads(manifest.read_text(encoding="utf-8"))
data["version"] = version
manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
constants = root / "custom_components/gismeteo_ha/const.py"
s = constants.read_text(encoding="utf-8")
s, count = re.subn(r'^(VERSION: Final = )"[^"\n]+"', rf'\g<1>"{version}"', s, count=1, flags=re.M)
if count != 1:
    raise SystemExit("Missing VERSION constant")
constants.write_text(s, encoding="utf-8")
print(f"Set integration version to {version}")
