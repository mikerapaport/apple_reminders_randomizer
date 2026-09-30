"""A small macOS desktop app for choosing a random Apple Reminder."""
from __future__ import annotations
import json
import random
import threading
import sys
from pathlib import Path
from dataclasses import asdict

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    if exc.name == "_tkinter":
        print(
            "This Python installation does not include Tkinter. For Homebrew Python 3.9, run:\n"
            "  brew install python-tk@3.9\n"
            "Then try: python3 app.py",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    raise

from reminders import Reminder, RemindersAccessError, fetch_reminders
from pdf_export import export_pdf

BG = "#f4f6f8"
INK = "#172b4d"
MUTED = "#5e6c84"
ACCENT = "#4263eb"

class ReminderRandomizer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Random Reminders")
        self.root.geometry("720x600")
        self.root.minsize(560, 480)
        self.root.configure(bg=BG)
        self.reminders: list[Reminder] = []
        self.current: Reminder | None = None
        self.include_completed = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Connect to Reminders to get started.")
        self._build()

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Helvetica Neue", 12))
        style.configure("Muted.TLabel", foreground=MUTED, font=("Helvetica Neue", 10))
        style.configure("Title.TLabel", font=("Helvetica Neue", 25, "bold"), foreground=INK)
        style.configure("TCheckbutton", background=BG, foreground=INK)
        outer = ttk.Frame(self.root, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Random Reminders", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Pick one open task from your Apple Reminders.", style="Muted.TLabel").pack(anchor="w", pady=(5, 18))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 18))
        ttk.Button(toolbar, text="Load from Reminders", command=self.load).pack(side="left")
        ttk.Button(toolbar, text="Export PDF", command=self.save_pdf).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Save JSON", command=self.save_json).pack(side="left")
        ttk.Checkbutton(toolbar, text="Include completed", variable=self.include_completed).pack(side="right")
        self.card = tk.Frame(outer, bg="white", highlightbackground="#dfe3e8", highlightthickness=1, padx=24, pady=24)
        self.card.pack(fill="both", expand=True)
        self.count = tk.StringVar(value="No reminders loaded")
        tk.Label(self.card, textvariable=self.count, bg="white", fg=MUTED, font=("Helvetica Neue", 10)).pack(anchor="w")
        self.title = tk.Label(self.card, text="Ready when you are", bg="white", fg=INK, font=("Helvetica Neue", 23, "bold"), wraplength=590, justify="left", anchor="w")
        self.title.pack(fill="x", pady=(25, 8))
        self.meta = tk.Label(self.card, text="", bg="white", fg=ACCENT, font=("Helvetica Neue", 11), justify="left", anchor="w")
        self.meta.pack(fill="x")
        self.notes = tk.Label(self.card, text="Load your reminders, then draw a task at random.", bg="white", fg=MUTED, font=("Helvetica Neue", 12), wraplength=590, justify="left", anchor="nw")
        self.notes.pack(fill="both", expand=True, pady=(20, 5))
        ttk.Button(outer, text="Pick a random task", command=self.pick).pack(fill="x", ipady=8, pady=(18, 10))
        ttk.Label(outer, textvariable=self.status, style="Muted.TLabel").pack(anchor="w")

    def load(self):
        self.status.set("Reading reminders…")
        threading.Thread(target=self._load_background, daemon=True).start()

    def _load_background(self):
        try:
            data = fetch_reminders()
            self.root.after(0, lambda: self._loaded(data))
        except RemindersAccessError as exc:
            self.root.after(0, lambda: self._load_failed(str(exc)))

    def _loaded(self, data):
        self.reminders = data
        self.current = None
        open_count = sum(not r.completed for r in data)
        self.count.set(f"{len(data)} reminders · {open_count} open")
        self.status.set("Reminders loaded. Choose your filters and draw a task.")
        self.title.configure(text="Ready when you are")
        self.meta.configure(text="")
        self.notes.configure(text="Your tasks and reminder details are ready.")

    def _load_failed(self, detail):
        self.status.set("Could not load reminders.")
        messagebox.showerror("Can't read Reminders", detail, parent=self.root)

    def _eligible(self):
        pool = self.reminders if self.include_completed.get() else [r for r in self.reminders if not r.completed]
        return [r for r in pool if r.title.strip()]

    def pick(self):
        pool = self._eligible()
        if not pool:
            messagebox.showinfo("No tasks available", "Load reminders, or include completed reminders, to choose a task.", parent=self.root)
            return
        self.current = random.choice(pool)
        item = self.current
        self.title.configure(text=item.title)
        details = [item.list_name]
        if item.due_date: details.append(f"Due {item.due_date}")
        if item.flagged: details.append("Flagged")
        if item.priority: details.append(f"Priority {item.priority}")
        if item.tags: details.append("Tags: " + ", ".join(item.tags))
        if item.completed: details.append("Completed")
        self.meta.configure(text="  ·  ".join(details))
        self.notes.configure(text=item.notes or "No notes for this reminder.")
        self.status.set(f"Picked from {len(pool)} eligible reminder{'s' if len(pool) != 1 else ''}.")

    def save_pdf(self):
        if not self.reminders:
            messagebox.showinfo("Nothing to export", "Load reminders first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export reminders as PDF", defaultextension=".pdf", filetypes=[("PDF document", "*.pdf")], initialfile="Apple Reminders.pdf")
        if not path: return
        try:
            export_pdf(self.reminders, path)
            self.status.set(f"PDF exported to {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("PDF export failed", str(exc), parent=self.root)

    def save_json(self):
        if not self.reminders:
            messagebox.showinfo("Nothing to export", "Load reminders first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Save reminder data", defaultextension=".json", filetypes=[("JSON file", "*.json")], initialfile="Apple Reminders.json")
        if not path: return
        Path(path).write_text(json.dumps([asdict(r) for r in self.reminders], ensure_ascii=False, indent=2), encoding="utf-8")
        self.status.set(f"JSON saved to {Path(path).name}")

def main():
    root = tk.Tk()
    ReminderRandomizer(root)
    root.mainloop()

if __name__ == "__main__":
    main()
