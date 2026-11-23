# MapTilesDownloader

Prepare an **offline satellite/street tile set** for the Evil-Cardputer **Map View**
(`src/mapview.h`). It downloads 256x256 raster tiles for a region into the exact SD
layout the firmware expects, so the map renders fully offline from the SD card.

---

## 🗺️ What it does

- Resolves a region from a **place name**, a **center + radius**, or a **bounding box**.
- Downloads tiles for a range of zoom levels (the firmware uses **13-17**).
- Writes them to the firmware layout:

  ```
  <out>/evil/maps/<z>/<x>/<y>.jpg   (satellite, JPEG)
  <out>/evil/maps/<z>/<x>/<y>.png   (street, PNG)
  ```

  The firmware tries `.jpg` first, then `.png`, so both layers can coexist.
- Then you copy the whole generated `evil/` folder to the **root of the SD card**
  (tiles land in `/evil/maps/`).

---

## 📡 Sources (`--source`)

| Source        | Format | Notes |
|---------------|--------|-------|
| `satellite`   | JPEG   | **ESRI World Imagery** (aerial). Recommended, tolerates caching. |
| `esri-street` | JPEG   | ESRI World Street map. |
| `osm`         | PNG    | OpenStreetMap street. **OSM blocks bulk downloads** and returns a blocked placeholder; keep regions tiny. |

---

## 🚀 Usage

Place name (area resolved automatically):

```bash
python3 map_tiles_downloader.py --place "Caen, France" --zoom 13 16 --out ./sd
python3 map_tiles_downloader.py --place "Calvados, France" --zoom 13 16 --out ./sd --yes
```

Center + radius:

```bash
python3 map_tiles_downloader.py --source satellite --lat 49.1829 --lon -0.3707 --radius-km 3 --zoom 13 17 --out ./sd
```

Bounding box (minlat minlon maxlat maxlon):

```bash
python3 map_tiles_downloader.py --source satellite --bbox 49.15 -0.42 49.21 -0.33 --zoom 13 17 --out ./sd
```

Then copy `./sd/evil/` to the SD card root.

---

## ⚠️ Notes

- **FAT32 SD cards only** (the firmware SD lib dislikes exFAT/NTFS).
- Higher zoom + larger region = many tiles. The tool prints an estimate and asks to
  confirm (use `--yes` to skip).
- **Attribution** (personal use): satellite = *"Esri, Maxar, Earthstar Geographics"*.
  Keep it.
