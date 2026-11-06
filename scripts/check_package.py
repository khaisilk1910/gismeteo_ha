"""Validate key Marketplace packaging contracts without requiring HA Core."""
from pathlib import Path
import json
import re
root = Path(__file__).resolve().parents[1]
folder=root/'custom_components'/'gismeteo_ha'
m=json.loads((folder/'manifest.json').read_text())
assert m['domain']=='gismeteo_ha'
assert re.fullmatch(r'\d+\.\d+\.\d+',m['version'])
assert (folder/'brand'/'icon.png').exists()
assert (folder/'frontend'/'gismeteo-ha-card.js').exists()
assert (root/'hacs.json').exists()
assert 'khaisilk1910/gismeteo_ha' in m['documentation']
print('Marketplace package checks passed')
