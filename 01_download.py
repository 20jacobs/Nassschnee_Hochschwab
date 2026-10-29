
# 01_download.py
# Sentinel-1 IW-GRD für den Hochschwab suchen und herunterladen

from pathlib import Path
from getpass import getpass
import requests
import pandas as pd

# ---------- Einstellungen ----------
OUT = Path("data/raw")
OUT.mkdir(parents=True, exist_ok=True)

START = "2024-11-01T00:00:00.000Z"
END   = "2025-07-01T00:00:00.000Z"

# Hochschwab: grobes Suchgebiet
WEST, SOUTH, EAST, NORTH = 15.0, 47.4, 15.4, 47.7

CATALOGUE = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)
DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products"

# ---------- Produktsuche ----------
polygon = (
    f"POLYGON(({WEST} {SOUTH},{EAST} {SOUTH},"
    f"{EAST} {NORTH},{WEST} {NORTH},"
    f"{WEST} {SOUTH}))"
)

filters = (
    "Collection/Name eq 'SENTINEL-1' and "
    "Attributes/OData.CSC.StringAttribute/any("
    "att:att/Name eq 'productType' and "
    "att/OData.CSC.StringAttribute/Value eq 'IW_GRDH_1S') and "
    f"ContentDate/Start ge {START} and "
    f"ContentDate/Start lt {END} and "
    "OData.CSC.Intersects("
    f"area=geography'SRID=4326;{polygon}')"
)

params = {
    "$filter": filters,
    "$orderby": "ContentDate/Start asc",
    "$top": 100,
    "$select": "Id,Name,ContentDate,GeoFootprint"
}

response = requests.get(CATALOGUE, params=params, timeout=120)
response.raise_for_status()
products = response.json()["value"]

if not products:
    raise RuntimeError(
        "Keine Treffer. Prüfe Zeitraum, Suchgebiet oder OData-Filter."
    )

df = pd.DataFrame(products)
df.to_csv("data/sentinel1_treffer.csv", index=False)

print(f"{len(df)} Produkte gefunden.")
print(df[["Name", "Id"]].to_string(index=False))

# Nur die gewünschten Szenen herunterladen.
# Bei vielen Treffern zuerst die CSV prüfen und diese Liste begrenzen.
answer = input("Alle Treffer herunterladen? (j/n): ").strip().lower()
if answer != "j":
    print("Abgebrochen. Trefferliste gespeichert.")
    raise SystemExit

# ---------- Zugangstoken ----------
username = input("CDSE-Benutzername: ")
password = getpass("CDSE-Passwort: ")

token_response = requests.post(
    TOKEN_URL,
    data={
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password"
    },
    timeout=60
)
token_response.raise_for_status()
token = token_response.json()["access_token"]

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {token}"})

# ---------- Download ----------
for i, product in enumerate(products, start=1):
    name = product["Name"]
    product_id = product["Id"]
    target = OUT / f"{name}.zip"

    if target.exists():
        print("Schon vorhanden:", target.name)
        continue

    url = f"{DOWNLOAD}({product_id})/$value"
    print(f"[{i}/{len(products)}] Lade {name}")

    with session.get(
        url, stream=True, allow_redirects=True, timeout=(30, 300)
    ) as r:
        r.raise_for_status()
        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    print("Gespeichert:", target)

print("Fertig. Rohdaten liegen in", OUT.resolve())
