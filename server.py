#!/usr/bin/env python3
import os
import xml.sax.saxutils as saxutils
from email.utils import formatdate
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PODCASTS_DIR = Path("podcasts")
PORT = 8888
FEED_TITLE = "Razorcake's podcast"
FEED_DESCRIPTION = "Razorcake'S podcast feed. All the razorcake podcasts are available through this feed."
CHUNK_SIZE = 64 * 1024  # 64 KB


def get_episodes():
    episodes = []
    for mp3 in PODCASTS_DIR.glob("*.mp3"):
        desc_file = mp3.with_suffix(".desc")
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.exists() else ""
        stat = mp3.stat()
        created = getattr(stat, "st_birthtime", stat.st_mtime)
        episodes.append({
            "title": mp3.stem.replace("_", " ").title(),
            "filename": mp3.name,
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
    ]
    for ep in episodes:
        pub_date = formatdate(ep["created"])
        file_url = f"{base_url}/podcasts/{ep['filename']}"
        first_line = ep["description"].splitlines()[0] if ep["description"] else ep["title"]
        lines += [
            "  <item>",
            f"    <title>{saxutils.escape(ep['title'])}</title>",
            f"    <description><![CDATA[{ep['description']}]]></description>",
            f"    <pubDate>{pub_date}</pubDate>",
            f"    <guid isPermaLink=\"false\">{saxutils.escape(file_url)}</guid>",
            f'    <enclosure url="{saxutils.escape(file_url)}" length="{ep["size"]}" type="audio/mpeg"/>',
            f"    <itunes:summary>{saxutils.escape(first_line)}</itunes:summary>",
            "  </item>",
        ]
    lines += ["</channel>", "</rss>"]
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get("Host", f"localhost:{PORT}")
        base_url = f"https://{host}:10666"

        if self.path in ("/", "/feed.rss"):
            body = generate_rss(base_url).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith("/podcasts/"):
            filename = self.path[len("/podcasts/"):]
            filepath = PODCASTS_DIR / filename
            if filepath.exists() and filepath.suffix == ".mp3":
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(filepath.stat().st_size))
                self.end_headers()
                with open(filepath, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        self.wfile.write(chunk)
            else:
                self.send_response(404)
                self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


if __name__ == "__main__":
    server = HTTPServer(("", PORT), Handler)
    print(f"RSS feed   → http://localhost:{PORT}/feed.rss")
    print(f"Podcasts   → {PODCASTS_DIR.absolute()}")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
