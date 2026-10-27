#!/usr/bin/env python3
"""Crée un fichier .guid à côté de chaque MP3 de podcasts/ à partir d'un ancien flux RSS.

Les épisodes sont associés par nom de fichier MP3 (fin de l'URL de <enclosure>).
Usage : python3 import_guids.py ancien_flux.xml   (fichier local ou URL)
"""
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

PODCASTS_DIR = Path("podcasts")


def read_feed(source):
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "AppleCoreMedia/1.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    return Path(source).read_bytes()


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = ET.fromstring(read_feed(sys.argv[1]))
    created = skipped = missing = 0
    for item in root.iter("item"):
        guid = item.findtext("guid")
        enclosure = item.find("enclosure")
        if not guid or enclosure is None:
            continue
        filename = enclosure.get("url", "").split("?")[0].rsplit("/", 1)[-1]
        mp3 = PODCASTS_DIR / filename
        if not mp3.exists():
            print(f"absent   {filename}")
            missing += 1
            continue
        guid_file = mp3.with_suffix(".guid")
        if guid_file.exists():
            skipped += 1
            continue
        guid_file.write_text(guid.strip() + "\n", encoding="utf-8")
        print(f"créé     {guid_file.name} → {guid.strip()}")
        created += 1
    print(f"{created} créé(s), {skipped} déjà présent(s), {missing} MP3 absent(s)")


if __name__ == "__main__":
    main()
