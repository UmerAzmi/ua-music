"""
organize.py
-----------
Scans a source music folder (any subfolder depth) and sorts every MP3 into:

    output/
        music/            — all 4 tags present: title, artist, album, cover art
        music-improper/   — has some tags but missing at least one of the 4
        music-untagged/   — no readable tags at all

Files in music/ are renamed:  Artist - Title.mp3
Files in music-improper/ and music-untagged/ keep their cleaned original name
so you can identify them easily when fixing tags.

Also writes  output/organize_log.txt  listing every file and what was missing.

NEW SONGS WORKFLOW
------------------
Put new downloads in a folder called  music-new/  (or any folder).
Run this script → choose mode 2 → it merges into existing output/ folders
without touching files already there.

Usage:
    python organize.py

Requirements:
    pip install mutagen
"""

import re
import shutil
from pathlib import Path

try:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, APIC
    from mutagen.mp3 import MP3
except ImportError:
    print("=" * 60)
    print("  Missing required library: mutagen")
    print("  Run:  pip install mutagen")
    print("=" * 60)
    input("\nPress Enter to exit...")
    raise SystemExit(1)


# ── helpers ───────────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    """Remove characters illegal in Windows filenames."""
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "unnamed"


def clean_original_name(path: Path) -> str:
    """Strip URL/site junk from the original filename."""
    stem = path.stem
    stem = re.sub(r'\(www\.[^)]+\)', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'\[www\.[^\]]+\]', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'https?://\S+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'www\.\S+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'_', ' ', stem)
    stem = re.sub(r'\s+', ' ', stem).strip()
    return sanitize(stem) or "unnamed"


def read_tags(mp3_path: Path) -> tuple:
    """
    Returns (tags dict, readable bool).
    tags keys: title, artist, album, has_cover
    readable=False means zero tags found → untagged bucket.
    """
    tags = {"title": "", "artist": "", "album": "", "has_cover": False}

    # Easy text tags
    try:
        easy = EasyID3(str(mp3_path))
        tags["title"]  = (easy.get("title",  [""])[0] or "").strip()
        tags["artist"] = (easy.get("artist", [""])[0] or "").strip()
        tags["album"]  = (easy.get("album",  [""])[0] or "").strip()
    except Exception:
        pass

    # Cover art (APIC frame)
    try:
        id3 = ID3(str(mp3_path))
        for key in id3.keys():
            if key.startswith("APIC") and id3[key].data:
                tags["has_cover"] = True
                break
    except Exception:
        pass

    readable = bool(tags["title"] or tags["artist"] or tags["album"])
    return tags, readable


def is_complete(tags: dict) -> bool:
    return bool(
        tags["title"] and
        tags["artist"] and
        tags["album"] and
        tags["has_cover"]
    )


def missing_fields(tags: dict) -> list:
    m = []
    if not tags["title"]:     m.append("title")
    if not tags["artist"]:    m.append("artist")
    if not tags["album"]:     m.append("album")
    if not tags["has_cover"]: m.append("cover art")
    return m


def unique_dest(dest_dir: Path, stem: str, suffix: str = ".mp3") -> Path:
    """Avoid overwriting: add (2), (3)… suffix if file already exists."""
    candidate = dest_dir / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = dest_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ── core ──────────────────────────────────────────────────────────────────────

def process(source_dir: Path, output_dir: Path):
    music_dir    = output_dir / "music"
    improper_dir = output_dir / "music-improper"
    untagged_dir = output_dir / "music-untagged"

    for d in (music_dir, improper_dir, untagged_dir):
        d.mkdir(parents=True, exist_ok=True)

    mp3_files = list(source_dir.rglob("*.mp3"))
    total = len(mp3_files)

    if total == 0:
        print(f"\n  No MP3 files found in: {source_dir}")
        return

    print(f"\n  Found {total} MP3 file(s). Sorting...\n")

    counts = {"music": 0, "improper": 0, "untagged": 0, "error": 0}
    log_lines = [
        f"organize.py — source: {source_dir.resolve()}",
        f"output:               {output_dir.resolve()}",
        "",
        f"{'FILE':<60}  RESULT",
        "-" * 100,
    ]

    for i, mp3 in enumerate(mp3_files, 1):
        try:
            tags, readable = read_tags(mp3)

            if not readable:
                clean = clean_original_name(mp3)
                dest  = unique_dest(untagged_dir, clean)
                shutil.copy2(str(mp3), str(dest))
                counts["untagged"] += 1
                log_lines.append(f"{mp3.name:<60}  [UNTAGGED]  →  {dest.name}")

            elif not is_complete(tags):
                clean = clean_original_name(mp3)
                dest  = unique_dest(improper_dir, clean)
                shutil.copy2(str(mp3), str(dest))
                counts["improper"] += 1
                missing = ", ".join(missing_fields(tags))
                log_lines.append(
                    f"{mp3.name:<60}  [IMPROPER]  →  {dest.name}  "
                    f"(missing: {missing})"
                )

            else:
                stem = f"{sanitize(tags['artist'])} - {sanitize(tags['title'])}"
                dest = unique_dest(music_dir, stem)
                shutil.copy2(str(mp3), str(dest))
                counts["music"] += 1
                log_lines.append(f"{mp3.name:<60}  [OK]  →  {dest.name}")

        except Exception as e:
            counts["error"] += 1
            log_lines.append(f"{mp3.name:<60}  [ERROR]  {e}")

        if i % 25 == 0 or i == total:
            pct = int(i / total * 100)
            bar = ("█" * (pct // 5)).ljust(20)
            print(f"  [{bar}] {pct:3d}%  ({i}/{total})")

    # Summary in log
    log_lines += [
        "",
        "=" * 100,
        "SUMMARY",
        f"  Properly tagged  (music/)           : {counts['music']}",
        f"  Improper tags    (music-improper/)  : {counts['improper']}",
        f"  No tags at all   (music-untagged/)  : {counts['untagged']}",
        f"  Errors                              : {counts['error']}",
    ]

    log_path = output_dir / "organize_log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print(f"""
  Done!

    music/            {counts['music']:>5} files  (properly tagged, renamed)
    music-improper/   {counts['improper']:>5} files  (fix tags, then re-run)
    music-untagged/   {counts['untagged']:>5} files  (no tags found)
    errors            {counts['error']:>5} files  (see log)

  Log saved to: {log_path.resolve()}
""")
    if counts["improper"]:
        print("  TIP: organize_log.txt lists exactly which tags are missing")
        print("       for every file in music-improper/\n")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Music Organizer — sorts MP3s by tag completeness")
    print("=" * 60)
    print("""
  [1]  First time — scan full music library
  [2]  Add new songs — scan music-new/ and merge into output/
""")
    mode = input("  Choose (1 or 2): ").strip()

    if mode == "2":
        default_src = Path.cwd() / "music-new"
    else:
        default_src = Path.cwd() / "music"

    default_out = Path.cwd() / "output"

    src_input = input(f"\n  Source folder [default: {default_src}]: ").strip()
    source_dir = Path(src_input) if src_input else default_src

    if not source_dir.exists():
        print(f"\n  ERROR: Folder not found: {source_dir}")
        input("Press Enter to exit...")
        raise SystemExit(1)

    out_input = input(f"  Output folder [default: {default_out}]: ").strip()
    output_dir = Path(out_input) if out_input else default_out

    print(f"""
  Source : {source_dir.resolve()}
  Output : {output_dir.resolve()}
           ├── music/
           ├── music-improper/
           └── music-untagged/
""")
    if input("  Proceed? (y/n): ").strip().lower() != "y":
        print("  Cancelled.")
        raise SystemExit(0)

    process(source_dir, output_dir)
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
