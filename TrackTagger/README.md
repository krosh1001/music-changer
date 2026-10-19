# TrackTagger — MP3 Metadata Studio

Windows GUI for reviewing and editing MP3 ID3 tags, searching MusicBrainz, and embedding release cover art.

## Features
- Scan a folder and subfolders for MP3 files.
- Edit artist, title, album, year, track number, and genre.
- Search MusicBrainz and choose a recording/release match.
- Download front cover art from Cover Art Archive when saving a selected release.
- Create timestamped backups before writing tags in `_TrackTagger_Backup`.
- Dark desktop interface; English labels.

## Run on Windows
Install Python 3.10 or newer, then double-click `run_windows.bat`, or run:

```powershell
py -m pip install -r requirements.txt
py app.py
```

## Build a standalone EXE
Double-click `build_exe.bat`. The executable will be created at `dist\TrackTagger.exe`.

## Notes
Internet access is required for MusicBrainz and cover lookups. Search uses existing tags and the filename; it does not identify a song from its audio fingerprint. Always review matches before saving. Bulk save writes tags for all scanned files, so use it only after reviewing them.
