from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/OpenCLIM/ecocrop/master/EcoCrop_DB.csv"
destination = Path(__file__).resolve().parent / "data/raw/ecocrop.csv"
destination.parent.mkdir(parents=True, exist_ok=True)
with urlopen(URL, timeout=30) as response:
    destination.write_bytes(response.read())
print(destination)
