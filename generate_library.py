"""
generate_library.py
Scans a flat music folder (MP3 + M4A), extracts cover art as separate JPG files,
and produces a lean library.json for the UA Music web app.

Defaults:
  Music folder : C:\Work\Project\Personal\UA Music\output\music
  Covers folder: C:\Work\Project\Personal\UA Music\output\covers
  Output JSON  : C:\Work\Project\Personal\UA Music\output\library.json
  R2 base URL  : https://pub-24dbba953b5b4b12a9fdbd968454f295.r2.dev
"""

import os
import json
import hashlib
import sys
from pathlib import Path

try:
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.easyid3 import EasyID3
    from mutagen import File as MutagenFile
except ImportError:
    print("ERROR: mutagen is not installed.")
    print("Run:  pip install mutagen")
    sys.exit(1)

# ─────────────────────────────────────────────
# DEFAULTS  (edit here or override at runtime)
# ─────────────────────────────────────────────
DEFAULT_MUSIC_FOLDER  = r"C:\Work\Project\Personal\UA Music\output\music"
DEFAULT_COVERS_FOLDER = r"C:\Work\Project\Personal\UA Music\output\covers"
DEFAULT_OUTPUT_JSON   = r"C:\Work\Project\Personal\UA Music\output\library.json"
DEFAULT_R2_BASE_URL   = "https://pub-24dbba953b5b4b12a9fdbd968454f295.r2.dev"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def ask(prompt, default):
    """Prompt user with a default value. Press Enter to accept default."""
    val = input(f"{prompt}\n  [{default}]: ").strip()
    return val if val else default


def make_id(artist, title, filename):
    """Generate a stable 12-char ID from artist + title + filename."""
    raw = f"{artist}|{title}|{filename}".lower()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def safe_filename(text):
    """Remove characters that are invalid in filenames."""
    for ch in r'\/:*?"<>|':
        text = text.replace(ch, "_")
    return text.strip()


def extract_cover_mp3(filepath):
    """Return raw cover bytes from an MP3, or None."""
    try:
        tags = ID3(filepath)
        for key in tags.keys():
            if key.startswith("APIC"):
                return tags[key].data, tags[key].mime
    except Exception:
        pass
    return None, None


def extract_cover_m4a(filepath):
    """Return raw cover bytes from an M4A/AAC, or None."""
    try:
        tags = MP4(filepath)
        covr = tags.get("covr")
        if covr:
            img = covr[0]
            mime = "image/jpeg" if img.imageformat == 13 else "image/png"
            return bytes(img), mime
    except Exception:
        pass
    return None, None


def save_cover(cover_data, mime, artist, album, covers_folder):
    """
    Save cover art to covers_folder as  Artist - Album.jpg
    Returns the filename (not full path), or None if already exists / save failed.
    """
    ext = ".jpg" if "jpeg" in mime.lower() else ".png"
    name = safe_filename(f"{artist} - {album}") + ext
    dest = Path(covers_folder) / name
    if not dest.exists():
        try:
            dest.write_bytes(cover_data)
        except Exception as e:
            print(f"    ⚠ Could not save cover: {e}")
            return None
    return name


def get_tags_mp3(filepath):
    """Return dict of tags from an MP3 file."""
    tags = {}
    try:
        easy = EasyID3(filepath)
        tags["title"]  = easy.get("title",  [""])[0]
        tags["artist"] = easy.get("artist", [""])[0]
        tags["album"]  = easy.get("album",  [""])[0]
        tags["year"]   = easy.get("date",   [""])[0][:4]
        tags["genre"]  = easy.get("genre",  [""])[0]
        tags["track"]  = easy.get("tracknumber", [""])[0].split("/")[0]
    except Exception:
        pass

    # Lyrics (USLT frame)
    try:
        raw = ID3(filepath)
        for key in raw.keys():
            if key.startswith("USLT"):
                tags["lyrics"] = str(raw[key])
                break
    except Exception:
        pass

    # Duration
    try:
        audio = MP3(filepath)
        tags["duration"] = round(audio.info.length, 2)
    except Exception:
        tags["duration"] = 0

    return tags


def get_tags_m4a(filepath):
    """Return dict of tags from an M4A file."""
    tags = {}
    try:
        audio = MP4(filepath)
        t = audio.tags or {}
        tags["title"]  = str(t.get("\xa9nam", [""])[0])
        tags["artist"] = str(t.get("\xa9ART", [""])[0])
        tags["album"]  = str(t.get("\xa9alb", [""])[0])
        tags["year"]   = str(t.get("\xa9day", [""])[0])[:4]
        tags["genre"]  = str(t.get("\xa9gen", [""])[0])
        trk = t.get("trkn", [(0, 0)])[0]
        tags["track"]  = str(trk[0]) if isinstance(trk, tuple) else str(trk)
        lyrics_tag = t.get("\xa9lyr", [""])
        if lyrics_tag and lyrics_tag[0]:
            tags["lyrics"] = str(lyrics_tag[0])
        tags["duration"] = round(audio.info.length, 2)
    except Exception:
        tags["duration"] = 0
    return tags


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  UA Music — Library Generator")
    print("=" * 60)
    print("\nPress Enter to accept the default value shown in [brackets].\n")

    music_folder  = ask("Path to flat music folder",  DEFAULT_MUSIC_FOLDER)
    covers_folder = ask("Path to save cover art JPGs", DEFAULT_COVERS_FOLDER)
    output_json   = ask("Path for output library.json", DEFAULT_OUTPUT_JSON)
    r2_base_url   = ask("R2 public base URL (no trailing slash)", DEFAULT_R2_BASE_URL).rstrip("/")

    music_folder  = Path(music_folder)
    covers_folder = Path(covers_folder)
    output_json   = Path(output_json)

    if not music_folder.exists():
        print(f"\nERROR: Music folder not found:\n  {music_folder}")
        sys.exit(1)

    covers_folder.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    # Collect all supported files
    extensions = {".mp3", ".m4a", ".aac"}
    files = sorted([
        f for f in music_folder.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not files:
        print(f"\nNo MP3/M4A files found in:\n  {music_folder}")
        sys.exit(1)

    print(f"\nFound {len(files)} files. Processing...\n")

    library    = []
    ok_count   = 0
    skip_count = 0
    cover_cache = {}   # "Artist - Album" → cover filename (avoid re-extracting)

    for i, filepath in enumerate(files, 1):
        ext = filepath.suffix.lower()
        fname = filepath.name

        print(f"  [{i:>4}/{len(files)}] {fname[:60]}", end="\r")

        # ── Read tags ──────────────────────────────────────────
        if ext == ".mp3":
            tags = get_tags_mp3(str(filepath))
            cover_data, cover_mime = extract_cover_mp3(str(filepath))
        else:  # .m4a / .aac
            tags = get_tags_m4a(str(filepath))
            cover_data, cover_mime = extract_cover_m4a(str(filepath))

        title  = tags.get("title",  "").strip()
        artist = tags.get("artist", "").strip()
        album  = tags.get("album",  "").strip()

        # Fallback title to filename stem if blank
        if not title:
            title = filepath.stem

        # ── Cover art ─────────────────────────────────────────
        cover_url = None
        if cover_data and artist and album:
            cache_key = f"{artist} - {album}"
            if cache_key in cover_cache:
                cover_filename = cover_cache[cache_key]
            else:
                cover_filename = save_cover(cover_data, cover_mime or "image/jpeg", artist, album, covers_folder)
                cover_cache[cache_key] = cover_filename

            if cover_filename:
                encoded = cover_filename.replace(" ", "%20")
                cover_url = f"{r2_base_url}/covers/{encoded}"

        # ── Build URL for the song ─────────────────────────────
        encoded_name = fname.replace(" ", "%20")
        song_url = f"{r2_base_url}/music/{encoded_name}"

        # ── Song entry ────────────────────────────────────────
        entry = {
            "id":       make_id(artist, title, fname),
            "title":    title,
            "artist":   artist,
            "album":    album,
            "year":     tags.get("year",  ""),
            "genre":    tags.get("genre", ""),
            "track":    tags.get("track", ""),
            "duration": tags.get("duration", 0),
            "url":      song_url,
            "filename": fname,
            "cover":    cover_url,
            "lyrics":   tags.get("lyrics", None)
        }

        library.append(entry)
        ok_count += 1

    # ── Write JSON ────────────────────────────────────────────
    print(f"\n\nWriting library.json ({ok_count} songs)...")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    json_size_mb = output_json.stat().st_size / (1024 * 1024)
    cover_count  = len(list(covers_folder.glob("*")))

    print("\n" + "=" * 60)
    print(f"  ✓ library.json  → {output_json}")
    print(f"    Size          : {json_size_mb:.2f} MB  (was ~1 GB before)")
    print(f"    Songs         : {ok_count}")
    print(f"  ✓ Covers folder → {covers_folder}")
    print(f"    Unique covers : {cover_count} JPG files")
    print("=" * 60)
    print("""
NEXT STEPS:
  1. Upload the 'covers' folder to your R2 bucket
     (same way you uploaded music — batches of 100 in the dashboard)
  2. Put library.json in your GitHub repo (it's small now)
  3. Deploy to Cloudflare Pages — done!

TO ADD A NEW SONG LATER:
  - Upload the MP3 to R2 in the music/ root
  - If it has a new album cover, upload the JPG to covers/
  - Add one entry to library.json following the existing format
  - Push library.json to GitHub — auto-deploys
""")


if __name__ == "__main__":
    main()
