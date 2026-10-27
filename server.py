#!/usr/bin/env python3
import os
import xml.sax.saxutils as saxutils
from email.utils import formatdate
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PODCASTS_DIR = Path("podcasts")
COVER_IMAGE = Path(__file__).resolve().parent / "Razorcakepodcast.jpg"
COVER_PATH = "/cover.jpg"
PORT = 8888
PUBLIC_PORT = 10666  # port exposé par le reverse proxy
MEDIA_TYPES = {".mp3": "audio/mpeg", ".jpg": "image/jpeg"}  # fichiers servis depuis podcasts/
FEED_TITLE = "Razorcake podcast"

FEED_DESCRIPTION = "Razorcake podcast feed. All the razorcake podcasts are available through this feed."
NEW_FEED_URL = "https://zorgul.com:10666/"  # itunes:new-feed-url, adresse définitive du flux
FEED_LANGUAGE = "en-us"
FEED_AUTHOR = "Razorcake"
FEED_OWNER_NAME = "Yann Bourdeau"
FEED_OWNER_EMAIL = "yann.bourdeau@pm.me"  # sert à Apple pour vérifier le propriétaire du flux
FEED_CATEGORY = "Music"  # catégorie Apple Podcasts
FEED_EXPLICIT = "true"  # "true" ou "false"
CHUNK_SIZE = 64 * 1024  # 64 KB


def get_episodes():
    episodes = []
    for mp3 in PODCASTS_DIR.glob("*.mp3"):
        desc_file = mp3.with_suffix(".desc")
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.exists() else ""
        image_file = mp3.with_suffix(".jpg")
        # GUID de l'ancien flux (PowerPress), pour que les applis ne voient pas l'épisode en double
        guid_file = mp3.with_suffix(".guid")
        guid = guid_file.read_text(encoding="utf-8").strip() if guid_file.exists() else None
        stat = mp3.stat()
        created = getattr(stat, "st_birthtime", stat.st_mtime)
        episodes.append({
            "title": mp3.stem.replace("_", " ").title(),
            "filename": mp3.name,
            "image": image_file.name if image_file.exists() else None,
            "guid": guid,
            "description": description,
            "created": created,
            "size": stat.st_size,
        })
    episodes.sort(key=lambda e: e["created"], reverse=True)
    return episodes


def generate_rss(base_url):
    episodes = get_episodes()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"'
        ' xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "<channel>",
        f"  <title>{saxutils.escape(FEED_TITLE)}</title>",
        f"  <description>{saxutils.escape(FEED_DESCRIPTION)}</description>",
        f"  <link>{saxutils.escape(base_url)}</link>",
        f"  <lastBuildDate>{formatdate()}</lastBuildDate>",
        f"  <itunes:new-feed-url>{saxutils.escape(NEW_FEED_URL)}</itunes:new-feed-url>",
        f"  <language>{FEED_LANGUAGE}</language>",
        f"  <itunes:author>{saxutils.escape(FEED_AUTHOR)}</itunes:author>",
        "  <itunes:owner>",
        f"    <itunes:name>{saxutils.escape(FEED_OWNER_NAME)}</itunes:name>",
        f"    <itunes:email>{saxutils.escape(FEED_OWNER_EMAIL)}</itunes:email>",
        "  </itunes:owner>",
        f'  <itunes:category text="{saxutils.escape(FEED_CATEGORY)}"/>',
        f"  <itunes:explicit>{FEED_EXPLICIT}</itunes:explicit>",
        "  <itunes:type>episodic</itunes:type>",
    ]
    if COVER_IMAGE.exists():
        cover_url = saxutils.escape(f"{base_url}{COVER_PATH}")
        lines += [
            "  <image>",
            f"    <url>{cover_url}</url>",
            f"    <title>{saxutils.escape(FEED_TITLE)}</title>",
            f"    <link>{saxutils.escape(base_url)}</link>",
            "  </image>",
            f'  <itunes:image href="{cover_url}"/>',
        ]
    for ep in episodes:
        pub_date = formatdate(ep["created"])
        file_url = f"{base_url}/podcasts/{ep['filename']}"
        first_line = ep["description"].splitlines()[0] if ep["description"] else ep["title"]
        guid = ep["guid"] or file_url
        lines += [
            "  <item>",
            f"    <title>{saxutils.escape(ep['title'])}</title>",
            f"    <description><![CDATA[{ep['description']}]]></description>",
            f"    <pubDate>{pub_date}</pubDate>",
            f"    <guid isPermaLink=\"false\">{saxutils.escape(guid)}</guid>",
            f'    <enclosure url="{saxutils.escape(file_url)}" length="{ep["size"]}" type="audio/mpeg"/>',
            f"    <itunes:summary>{saxutils.escape(first_line)}</itunes:summary>",
        ]
        if ep["image"]:
            image_url = f"{base_url}/podcasts/{ep['image']}"
            lines.append(f'    <itunes:image href="{saxutils.escape(image_url)}"/>')
        lines.append("  </item>")
    lines += ["</channel>", "</rss>"]
    return "\n".join(lines)


def parse_range(header, size):
    """Analyse un en-tête « Range: bytes=début-fin ».

    Retourne (début, fin) inclus, None sans en-tête (ou si non géré, ex. plusieurs plages),
    ou "invalid" si la plage est hors du fichier (réponse 416).
    """
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    start_s, _, end_s = header[len("bytes="):].strip().partition("-")
    try:
        if start_s == "":  # bytes=-500 : les 500 derniers octets
            suffix = int(end_s)
            if suffix == 0:
                return "invalid"
            return max(size - suffix, 0), size - 1
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start >= size or end < start:
        return "invalid"
    return start, min(end, size - 1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get("Host", "localhost")
        # Retire le port éventuel du Host pour toujours utiliser PUBLIC_PORT
        if host.startswith("["):  # IPv6, ex. [::1]:8888
            host = host[:host.find("]") + 1]
        else:
            host = host.split(":")[0]
        base_url = f"https://{host}:{PUBLIC_PORT}"

        if self.path in ("/", "/feed.rss"):
            body = generate_rss(base_url).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == COVER_PATH and COVER_IMAGE.exists():
            body = COVER_IMAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith("/podcasts/"):
            filename = self.path[len("/podcasts/"):]
            filepath = PODCASTS_DIR / filename
            content_type = MEDIA_TYPES.get(filepath.suffix)
            # Refuse les chemins qui sortent du répertoire podcasts (ex. ../)
            in_podcasts_dir = filepath.resolve().parent == PODCASTS_DIR.resolve()
            if content_type and in_podcasts_dir and filepath.is_file():
                self.send_file(filepath, content_type)
            else:
                self.send_response(404)
                self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def send_file(self, filepath, content_type):
        """Envoie un fichier, en entier ou la plage demandée par l'en-tête Range (206)."""
        size = filepath.stat().st_size
        byte_range = parse_range(self.headers.get("Range"), size)
        if byte_range == "invalid":
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        start, end = byte_range or (0, size - 1)
        length = end - start + 1

        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if byte_range:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        try:
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0 and (chunk := f.read(min(CHUNK_SIZE, remaining))):
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # le lecteur a fermé la connexion (avance rapide, pause) : normal

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"RSS feed   → http://localhost:{PORT}/feed.rss")
    print(f"Podcasts   → {PODCASTS_DIR.absolute()}")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
