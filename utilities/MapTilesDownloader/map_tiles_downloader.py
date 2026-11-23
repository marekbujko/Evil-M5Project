#!/usr/bin/env python3
"""
map_tiles_downloader.py - Prepare an offline tile set for the Evil-Cardputer map view.

Downloads 256x256 raster tiles for a region into the SD layout the firmware expects:

    <out>/evil/maps/<z>/<x>/<y>.<ext>      (.jpg for satellite, .png for street)

Then copy the whole `evil/` folder to the SD card root (tiles land in /evil/maps/). The firmware tries .jpg first,
then .png, so both layers can coexist.

Sources (--source):
    satellite  ESRI World Imagery  (JPEG)  -- aerial/satellite, tolerates offline caching
    osm        OpenStreetMap       (PNG)   -- street map; WARNING: OSM blocks bulk downloads
                                             and returns a "blocked" placeholder. Keep regions
                                             tiny or it will refuse. Satellite is recommended.
    esri-street ESRI World Street   (JPEG)

Usage (le plus simple - nom de lieu, zone resolue automatiquement):
    python3 map_tiles_downloader.py --place "Caen, France" --zoom 13 16 --out ./sd
    python3 map_tiles_downloader.py --place "Calvados, France" --zoom 13 16 --out ./sd --yes

Usage (center + radius):
    python3 map_tiles_downloader.py --source satellite --lat 49.1829 --lon -0.3707 --radius-km 3 --zoom 13 17 --out ./sd

Usage (bounding box):
    python3 map_tiles_downloader.py --source satellite --bbox 49.15 -0.42 49.21 -0.33 --zoom 13 17 --out ./sd

Attribution: satellite = "Esri, Maxar, Earthstar Geographics". Keep it for personal use.
FAT32 SD cards only (the firmware's SD lib dislikes exFAT/NTFS).
"""
import argparse, hashlib, json, math, os, sys, time, urllib.parse, urllib.request

# name -> (url template with {z}{x}{y}, extension)
SOURCES = {
    "satellite":   ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", "jpg"),
    "esri-street": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", "jpg"),
    "osm":         ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "png"),
}
UA = "EvilCardputer-MapTool/1.0 (offline map for personal device)"   # no personal info
# md5 of the OSM "tile download blocked" placeholder (all-identical bulk-block image)
OSM_BLOCKED_MD5 = "8e8d1ff492c2bdae445a83ccdb8e449f"

def deg2tile(lat, lon, z):
    lat_r = math.radians(lat); n = 2 ** z
    xt = int((lon + 180.0) / 360.0 * n)
    yt = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, xt)), max(0, min(n - 1, yt))

def bbox_from_center(lat, lon, radius_km):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.01, math.cos(math.radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)

def geocode_place(name):
    """Resolve a place name (city, department, region...) to a bbox via OpenStreetMap Nominatim.
    Returns (latmin, lonmin, latmax, lonmax). One polite request, no personal data sent."""
    q = urllib.parse.urlencode({"q": name, "format": "json", "limit": 1})
    url = "https://nominatim.openstreetmap.org/search?" + q
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR: geocoding failed for '{name}': {e}", file=sys.stderr); sys.exit(4)
    if not res:
        print(f"ERROR: place '{name}' not found. Try a more precise name, e.g. \"Caen, France\".", file=sys.stderr)
        sys.exit(4)
    hit = res[0]
    # Nominatim boundingbox = [latmin, latmax, lonmin, lonmax] (strings)
    bb = hit.get("boundingbox")
    print(f"Place: {hit.get('display_name','?')}")
    return (float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3]))

def main():
    ap = argparse.ArgumentParser(description="Download offline map tiles for the Evil-Cardputer")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--place", help='place name, auto-resolved to a zone, e.g. --place "Calvados, France"')
    g.add_argument("--bbox", nargs=4, type=float, metavar=("LATMIN", "LONMIN", "LATMAX", "LONMAX"))
    g.add_argument("--lat", type=float, help="center (with --lon --radius-km)")
    ap.add_argument("--lon", type=float)
    ap.add_argument("--radius-km", type=float, default=2.0)
    ap.add_argument("--zoom", nargs=2, type=int, default=[13, 16], metavar=("ZMIN", "ZMAX"))
    ap.add_argument("--out", default="./sd", help="output dir (maps/ created inside)")
    ap.add_argument("--source", choices=list(SOURCES), default="satellite")
    ap.add_argument("--server", help="override url template {z}/{x}/{y} (keeps --source extension)")
    ap.add_argument("--delay", type=float, default=0.08, help="pause between requests (s)")
    ap.add_argument("--max", type=int, default=6000, help="guard on tile count")
    ap.add_argument("--yes", action="store_true", help="skip the tile-count guard and download anyway")
    a = ap.parse_args()

    if a.lat is not None and a.lon is None:
        ap.error("--lat requires --lon")
    tmpl, ext = SOURCES[a.source]
    if a.server:
        tmpl = a.server
    if a.place:
        latmin, lonmin, latmax, lonmax = geocode_place(a.place)
    elif a.bbox:
        latmin, lonmin, latmax, lonmax = a.bbox
    else:
        latmin, lonmin, latmax, lonmax = bbox_from_center(a.lat, a.lon, a.radius_km)

    zmin, zmax = a.zoom
    jobs = []
    for z in range(zmin, zmax + 1):
        x0, y0 = deg2tile(latmax, lonmin, z)
        x1, y1 = deg2tile(latmin, lonmax, z)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                jobs.append((z, x, y))
    print(f"Source: {a.source} (.{ext})  zoom {zmin}-{zmax}")
    print(f"Zone: lat[{latmin:.4f},{latmax:.4f}] lon[{lonmin:.4f},{lonmax:.4f}]")
    print(f"Tiles: {len(jobs)}  (~{len(jobs)*15/1024:.1f} MB est.)")
    if len(jobs) > a.max and not a.yes:
        est_h = len(jobs) * a.delay / 3600.0
        print(f"\nSTOP: {len(jobs)} tiles > guard --max {a.max} (~{len(jobs)*15/1024:.0f} MB, ~{est_h:.1f} h de download).", file=sys.stderr)
        print(f"  -> pour lancer quand meme : rajoute  --yes", file=sys.stderr)
        print(f"  -> ou reduis la zone / la plage de zoom (ex: --zoom 13 15 au lieu de 13 17)", file=sys.stderr)
        sys.exit(2)

    base = os.path.join(a.out, "evil", "maps")
    ok = skip = fail = blocked = 0
    hashes = {}
    for i, (z, x, y) in enumerate(jobs, 1):
        d = os.path.join(base, str(z), str(x))
        p = os.path.join(d, f"{y}.{ext}")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            skip += 1; continue
        os.makedirs(d, exist_ok=True)
        url = tmpl.format(z=z, x=x, y=y)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            md5 = hashlib.md5(data).hexdigest()
            if md5 == OSM_BLOCKED_MD5:
                blocked += 1
                if blocked <= 3:
                    print(f"\n  BLOCKED placeholder at {z}/{x}/{y} (source is refusing bulk)", file=sys.stderr)
                if blocked >= 20:
                    print(f"\nABORT: source returned {blocked} 'blocked' placeholders. "
                          f"Use --source satellite (ESRI) instead of OSM.", file=sys.stderr)
                    sys.exit(3)
                continue
            # sanity: must be a real image (PNG or JPEG magic)
            if not (data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff"):
                fail += 1
                if fail <= 3: print(f"\n  not an image at {z}/{x}/{y} ({len(data)}o)", file=sys.stderr)
                continue
            hashes[md5] = hashes.get(md5, 0) + 1
            with open(p, "wb") as fo:
                fo.write(data)
            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5: print(f"\n  KO {z}/{x}/{y}: {e}", file=sys.stderr)
        if i % 25 == 0 or i == len(jobs):
            print(f"  {i}/{len(jobs)}  ok={ok} skip={skip} blocked={blocked} fail={fail}", end="\r")
        time.sleep(a.delay)

    # placeholder guard: if nearly all saved tiles are identical, it was a block
    uniq = len(hashes); total_saved = sum(hashes.values())
    print(f"\nDone: {ok} saved, {skip} existing, {blocked} blocked, {fail} failed -> {base}")
    if total_saved >= 20 and uniq <= max(2, total_saved // 50):
        print(f"WARNING: only {uniq} distinct images among {total_saved} tiles -> likely a "
              f"blocked/placeholder layer. Check the tiles.", file=sys.stderr)
    print("Copy the 'evil/maps/' folder to the SD card (merge into /evil/).")

if __name__ == "__main__":
    main()
