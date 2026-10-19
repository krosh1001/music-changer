import io
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import xml.etree.ElementTree as ET

from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TRCK, TCON, APIC
from mutagen.mp3 import MP3

APP_NAME = "TrackTagger"
MUSICBRAINZ = "https://musicbrainz.org/ws/2/recording/"
COVER_ART = "https://coverartarchive.org/release/{}/front-500"
USER_AGENT = "TrackTagger/1.0 (desktop MP3 tag editor)"


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml, image/*, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", "")


def clean_query(value):
    return re.sub(r"\s+", " ", value or "").strip()


def search_musicbrainz(query):
    params = urllib.parse.urlencode({"query": query, "fmt": "xml", "limit": 8, "inc": "genres"})
    data, _ = http_get(MUSICBRAINZ + "?" + params)
    root = ET.fromstring(data)
    ns = {"m": "http://musicbrainz.org/ns/mmd-2.0#"}
    results = []
    for rec in root.findall(".//m:recording", ns):
        title = rec.findtext("m:title", default="", namespaces=ns)
        artist = ""
        album = ""
        year = ""
        release_id = ""
        genre_nodes = rec.findall("m:genre-list/m:genre/m:name", ns)
        genre = ", ".join([node.text for node in genre_nodes if node.text][:3])
        artist_credit = rec.find("m:artist-credit", ns)
        if artist_credit is not None:
            names = []
            for name in artist_credit.findall("m:name-credit/m:artist/m:name", ns):
                if name.text:
                    names.append(name.text)
            artist = ", ".join(names)
        release = rec.find("m:release-list/m:release", ns)
        if release is not None:
            release_id = release.attrib.get("id", "")
            album = release.findtext("m:title", default="", namespaces=ns)
            date = release.findtext("m:date", default="", namespaces=ns)
            year = date[:4] if date else ""
        results.append({"title": title, "artist": artist, "album": album, "year": year, "genre": genre, "release_id": release_id})
    return results


class TrackTagger(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TrackTagger • MP3 metadata studio")
        self.geometry("1120x720")
        self.minsize(900, 580)
        self.configure(bg="#111827")
        self.tracks = []
        self.current_folder = None
        self._style()
        self._build_ui()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#111827")
        style.configure("Panel.TFrame", background="#1f2937")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#111827", foreground="#9ca3af")
        style.configure("Title.TLabel", background="#111827", foreground="#f9fafb", font=("Segoe UI Semibold", 22))
        style.configure("Sub.TLabel", background="#111827", foreground="#9ca3af", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(12, 8), background="#374151", foreground="#f9fafb")
        style.map("TButton", background=[("active", "#4b5563")])
        style.configure("Accent.TButton", background="#7c3aed", foreground="white")
        style.map("Accent.TButton", background=[("active", "#6d28d9")])
        style.configure("Treeview", background="#1f2937", fieldbackground="#1f2937", foreground="#e5e7eb", rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background="#374151", foreground="#f9fafb", font=("Segoe UI Semibold", 9), padding=8)
        style.map("Treeview", background=[("selected", "#4c1d95")], foreground=[("selected", "white")])
        style.configure("TEntry", fieldbackground="#374151", foreground="#f9fafb", insertcolor="white", padding=7)

    def _build_ui(self):
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="TrackTagger", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="MP3 METADATA STUDIO  •  Find tags, review matches, save safely", style="Sub.TLabel").pack(anchor="w", pady=(3, 0))

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 14))
        ttk.Button(toolbar, text="📁  Choose folder", style="Accent.TButton", command=self.choose_folder).pack(side="left")
        ttk.Button(toolbar, text="↻  Rescan", command=self.rescan).pack(side="left", padx=(8, 0))
        self.folder_label = ttk.Label(toolbar, text="No folder selected", style="Muted.TLabel")
        self.folder_label.pack(side="left", padx=14)
        self.count_label = ttk.Label(toolbar, text="0 MP3 files")
        self.count_label.pack(side="right")

        table_frame = ttk.Frame(root, style="Panel.TFrame", padding=8)
        table_frame.pack(fill="both", expand=True)
        columns = ("file", "artist", "title", "album", "year", "status")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        labels = {"file": "FILE", "artist": "ARTIST", "title": "TITLE", "album": "ALBUM", "year": "YEAR", "status": "STATUS"}
        widths = {"file": 240, "artist": 150, "title": 190, "album": 170, "year": 65, "status": 110}
        for col in columns:
            self.table.heading(col, text=labels[col])
            self.table.column(col, width=widths[col], minwidth=55, anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", self.on_select)
        self.table.bind("<Double-1>", lambda _e: self.search_selected())

        lower = ttk.Frame(root)
        lower.pack(fill="x", pady=(14, 0))
        edit = ttk.Frame(lower, style="Panel.TFrame", padding=14)
        edit.pack(side="left", fill="both", expand=True)
        ttk.Label(edit, text="EDIT TAGS", background="#1f2937", foreground="#a78bfa", font=("Segoe UI Semibold", 9)).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 9))
        self.fields = {}
        specs = [("artist", "Artist"), ("title", "Title"), ("album", "Album"), ("year", "Year"), ("track", "Track #"), ("genre", "Genre")]
        for i, (key, label) in enumerate(specs):
            row, col = divmod(i, 3)
            cell = ttk.Frame(edit, style="Panel.TFrame")
            cell.grid(row=row + 1, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0), pady=4)
            ttk.Label(cell, text=label, background="#1f2937", foreground="#9ca3af").pack(anchor="w")
            ent = ttk.Entry(cell)
            ent.pack(fill="x", pady=(3, 0))
            self.fields[key] = ent
            edit.columnconfigure(col, weight=1)
        actions = ttk.Frame(lower, padding=(14, 0, 0, 0))
        actions.pack(side="right", fill="y")
        ttk.Button(actions, text="⌕  Search MusicBrainz", style="Accent.TButton", command=self.search_selected).pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Apply match", command=self.apply_match).pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Save tags + cover", command=self.save_selected).pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Save all edited", command=self.save_all).pack(fill="x")
        self.status = tk.StringVar(value="Ready • Select a folder to begin")
        ttk.Label(root, textvariable=self.status, style="Muted.TLabel").pack(anchor="w", pady=(12, 0))

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Choose folder containing MP3 files")
        if folder:
            self.current_folder = Path(folder)
            self.folder_label.configure(text=str(self.current_folder))
            self.scan_folder()

    def rescan(self):
        if self.current_folder:
            self.scan_folder()

    def scan_folder(self):
        for item in self.table.get_children():
            self.table.delete(item)
        self.tracks.clear()
        files = sorted(self.current_folder.rglob("*.mp3"))
        for path in files:
            track = {"path": path, "match": None, "cover": None}
            self._read_tags(track)
            self.tracks.append(track)
            self.table.insert("", "end", iid=str(len(self.tracks)-1), values=(
                path.name, track.get("artist", ""), track.get("title", ""), track.get("album", ""),
                track.get("year", ""), "Ready"))
        self.count_label.configure(text=f"{len(files)} MP3 files")
        self.status.set(f"Scanned {len(files)} MP3 file(s)")
        if not files:
            messagebox.showinfo(APP_NAME, "No MP3 files found in this folder.")

    def _read_tags(self, track):
        try:
            tags = ID3(track["path"])
        except (ID3NoHeaderError, OSError):
            tags = ID3()
        def get(frame):
            obj = tags.get(frame)
            return str(obj.text[0]) if obj and obj.text else ""
        track.update({
            "artist": get("TPE1"), "title": get("TIT2"), "album": get("TALB"),
            "year": get("TDRC")[:4], "track": get("TRCK"), "genre": get("TCON"),
        })

    def selected_track(self):
        selection = self.table.selection()
        if not selection:
            return None
        return self.tracks[int(selection[0])]

    def on_select(self, _event=None):
        track = self.selected_track()
        if not track:
            return
        for key, entry in self.fields.items():
            entry.delete(0, "end")
            entry.insert(0, track.get(key, ""))
        self.status.set(track["path"].name)

    def _read_fields(self, track):
        for key, entry in self.fields.items():
            track[key] = entry.get().strip()

    def search_selected(self):
        track = self.selected_track()
        if not track:
            messagebox.showinfo(APP_NAME, "Select an MP3 file first.")
            return
        self._read_fields(track)
        query = clean_query(f'recording:"{track.get("title") or track["path"].stem}" AND artist:"{track.get("artist", "")}"')
        self.status.set("Searching MusicBrainz…")
        threading.Thread(target=self._search_worker, args=(track, query), daemon=True).start()

    def _search_worker(self, track, query):
        try:
            results = search_musicbrainz(query)
            if not results:
                fallback = track.get("title") or track["path"].stem
                results = search_musicbrainz(fallback)
            self.after(0, lambda: self._show_results(track, results))
        except Exception as exc:
            self.after(0, lambda err=exc: self.status.set(f"Search failed: {err}"))
            self.after(0, lambda err=exc: messagebox.showerror(APP_NAME, f"MusicBrainz search failed.\n{err}\n\nCheck your internet connection and try again."))

    def _show_results(self, track, results):
        if not results:
            self.status.set("No matches found")
            messagebox.showinfo(APP_NAME, "No MusicBrainz matches found. You can still edit tags manually.")
            return
        win = tk.Toplevel(self)
        win.title("Choose MusicBrainz match")
        # Roomy, resizable picker keeps the action button visible without manual resizing.
        win.geometry("1100x620")
        win.minsize(900, 480)
        win.resizable(True, True)
        win.configure(bg="#111827")
        win.transient(self)
        ttk.Label(win, text="Select the correct recording / release", style="Title.TLabel").pack(anchor="w", padx=16, pady=14)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=("artist", "title", "album", "year"), show="headings", selectmode="browse")
        for col, width in [("artist", 220), ("title", 270), ("album", 360), ("year", 90)]:
            tree.heading(col, text=col.upper())
            tree.column(col, width=width, minwidth=90, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        for i, result in enumerate(results):
            tree.insert("", "end", iid=str(i), values=(result["artist"], result["title"], result["album"], result["year"]))
        def choose():
            sel = tree.selection()
            if not sel:
                return
            track["match"] = results[int(sel[0])]
            result = track["match"]
            for key in ("artist", "title", "album", "year"):
                track[key] = result.get(key, "")
            self._update_row(track)
            if self.selected_track() is track:
                self.on_select()
            self.status.set("Match selected — review tags, then save")
            win.destroy()
        footer = ttk.Frame(win, padding=(16, 0, 16, 14))
        footer.pack(fill="x")
        ttk.Label(footer, text=f"{len(results)} matches • Double-click a row or select it and confirm", style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="Use selected match", style="Accent.TButton", command=choose).pack(side="right")
        tree.bind("<Double-1>", lambda _event: choose())
        if results:
            tree.selection_set("0")
            tree.focus("0")
        # Center the dialog on screen at its initial size.
        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() - win.winfo_width()) // 2)
        y = max(0, (win.winfo_screenheight() - win.winfo_height()) // 2)
        win.geometry("+" + str(x) + "+" + str(y))

    def apply_match(self):
        track = self.selected_track()
        if not track or not track.get("match"):
            messagebox.showinfo(APP_NAME, "Search MusicBrainz and choose a match first.")
            return
        self.on_select()
        self.status.set("Match applied to editor. Save to write tags.")

    def _update_row(self, track):
        idx = self.tracks.index(track)
        self.table.item(str(idx), values=(track["path"].name, track.get("artist",""), track.get("title",""),
                                          track.get("album",""), track.get("year",""), "Match selected"))

    def _backup(self, path):
        backup_dir = path.parent / "_TrackTagger_Backup"
        backup_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"{path.stem}.{stamp}.mp3"
        shutil.copy2(path, target)

    def save_selected(self):
        track = self.selected_track()
        if not track:
            messagebox.showinfo(APP_NAME, "Select an MP3 file first.")
            return
        self._read_fields(track)
        try:
            self._save_track(track)
            self._update_row(track)
            self.status.set(f"Saved tags: {track['path'].name}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save tags:\n{exc}")

    def _save_track(self, track):
        path = track["path"]
        self._backup(path)
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        frames = {
            "artist": ("TPE1", TPE1), "title": ("TIT2", TIT2), "album": ("TALB", TALB),
            "year": ("TDRC", TDRC), "track": ("TRCK", TRCK), "genre": ("TCON", TCON)
        }
        for key, (frame_id, cls) in frames.items():
            tags.delall(frame_id)
            if track.get(key):
                tags.add(cls(encoding=3, text=track[key]))
        cover = track.get("cover")
        release_id = (track.get("match") or {}).get("release_id")
        if cover is None and release_id:
            try:
                cover, _ = http_get(COVER_ART.format(release_id), timeout=12)
            except Exception:
                cover = None
        if cover:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
        tags.save(path, v2_version=3)

    def save_all(self):
        if not self.tracks:
            messagebox.showinfo(APP_NAME, "Scan a folder first.")
            return
        if not messagebox.askyesno(APP_NAME, f"Save tags for all {len(self.tracks)} scanned MP3 files?\nBackups will be created first."):
            return
        saved, errors = 0, []
        for track in self.tracks:
            try:
                self._save_track(track)
                self._update_row(track)
                saved += 1
            except Exception as exc:
                errors.append(f"{track['path'].name}: {exc}")
        self.status.set(f"Saved {saved}; errors {len(errors)}")
        if errors:
            messagebox.showwarning(APP_NAME, f"Saved {saved} file(s), {len(errors)} failed:\n\n" + "\n".join(errors[:8]))
        else:
            messagebox.showinfo(APP_NAME, f"Successfully saved tags for {saved} MP3 file(s).")


if __name__ == "__main__":
    app = TrackTagger()
    app.mainloop()
