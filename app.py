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
    from tkinter import filedialog, messagebox
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
        self.generate_after_load = False
        self.loading = False
        self.include_completed = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Click Generate Task to load your reminders and choose one.")
        self._build()

    def _build(self):
        outer = tk.Frame(self.root, bg=BG, padx=28, pady=24)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Random Reminders", bg=BG, fg=INK,
                 font=("Helvetica Neue", 25, "bold")).pack(anchor="w")
        tk.Label(outer, text="Get one task from your Apple Reminders.", bg=BG, fg=MUTED,
                 font=("Helvetica Neue", 11)).pack(anchor="w", pady=(5, 16))

        toolbar = tk.Frame(outer, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        tk.Button(toolbar, text="Load / Refresh Reminders", command=self.load,
                  padx=10, pady=5).pack(side="left")
        tk.Button(toolbar, text="Export PDF", command=self.save_pdf,
                  padx=10, pady=5).pack(side="left", padx=(8, 0))
        tk.Button(toolbar, text="Save JSON", command=self.save_json,
                  padx=10, pady=5).pack(side="left", padx=(8, 0))
        tk.Checkbutton(toolbar, text="Include completed", variable=self.include_completed,
                       bg=BG, fg=INK, activebackground=BG).pack(side="right")

        self.count = tk.StringVar(value="No reminders loaded")
        tk.Label(outer, textvariable=self.count, bg=BG, fg=MUTED,
                 font=("Helvetica Neue", 10)).pack(anchor="w", pady=(0, 8))

        self.card = tk.Frame(outer, bg="white", highlightbackground="#dfe3e8",
                             highlightthickness=1, padx=22, pady=20)
        self.card.pack(fill="both", expand=True)
        self.title = tk.Label(self.card, text="Ready when you are", bg="white", fg=INK,
                              font=("Helvetica Neue", 22, "bold"), wraplength=590,
                              justify="left", anchor="w")
        self.title.pack(fill="x", anchor="w")
        self.source = tk.Label(self.card, text="Source list: —", bg="white", fg=ACCENT,
                               font=("Helvetica Neue", 12, "bold"), anchor="w")
        self.source.pack(fill="x", pady=(9, 13))
        tk.Frame(self.card, bg="#e5e9f0", height=1).pack(fill="x", pady=(0, 12))
        self.details = tk.Text(self.card, height=10, wrap="word", bg="white", fg=INK,
                               font=("Helvetica Neue", 11), relief="flat", borderwidth=0,
                               padx=0, pady=0, state="disabled", takefocus=False)
        self.details.pack(fill="both", expand=True)
        self._show_details("Click Generate Task to load reminders and display a random task here.")

        tk.Button(outer, text="Generate Task", command=self.generate_task,
                  bg=ACCENT, fg="white", activebackground="#3451c6", activeforeground="white",
                  font=("Helvetica Neue", 14, "bold"), relief="flat", padx=12, pady=11,
                  cursor="pointinghand").pack(fill="x", pady=(14, 9))
        tk.Label(outer, textvariable=self.status, bg=BG, fg=MUTED,
                 font=("Helvetica Neue", 10), anchor="w").pack(fill="x")

    def _show_details(self, text: str):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def load(self, generate_when_ready=False):
        if self.loading:
            self.generate_after_load = self.generate_after_load or generate_when_ready
            return
        self.loading = True
        self.generate_after_load = generate_when_ready
        self.status.set("Reading reminders…")
        threading.Thread(target=self._load_background, daemon=True).start()

    def _load_background(self):
        try:
            data = fetch_reminders()
            self.root.after(0, lambda: self._loaded(data))
        except RemindersAccessError as exc:
            self.root.after(0, lambda detail=str(exc): self._load_failed(detail))
        except Exception as exc:
            detail = f"Unexpected error while reading Reminders: {exc}"
            self.root.after(0, lambda detail=detail: self._load_failed(detail))

    def _loaded(self, data):
        self.loading = False
        self.reminders = data
        self.current = None
        open_count = sum(not r.completed for r in data)
        self.count.set(f"{len(data)} reminders · {open_count} open")
        self.status.set("Reminders loaded. Choose your filters and draw a task.")
        self.title.configure(text="Ready when you are")
        self.source.configure(text="Source list: —")
        self._show_details("Reminder data loaded. Click Generate Task to choose one.")
        if self.generate_after_load:
            self.generate_after_load = False
            self.pick()

    def _load_failed(self, detail):
        self.loading = False
        self.generate_after_load = False
        self.status.set("Could not load reminders.")
        messagebox.showerror("Can't read Reminders", detail, parent=self.root)

    def _eligible(self):
        pool = self.reminders if self.include_completed.get() else [r for r in self.reminders if not r.completed]
        return [r for r in pool if r.title.strip()]

    def generate_task(self):
        if not self.reminders:
            self.load(generate_when_ready=True)
            return
        self.pick()

    def pick(self):
        pool = self._eligible()
        if not pool:
            messagebox.showinfo("No tasks available", "Load reminders, or include completed reminders, to choose a task.", parent=self.root)
            return
        self.current = random.choice(pool)
        item = self.current
        self.title.configure(text=item.title)
        self.source.configure(text=f"Source list: {item.list_name or 'Unspecified'}")
        priority_names = {0: "None", 1: "Low", 5: "Medium", 9: "High"}
        rows = [
            ("Notes", item.notes or "None"),
            ("Due", item.due_date or "Not set"),
            ("Status", "Completed" if item.completed else "Open"),
            ("Flagged", "Yes" if item.flagged else "No"),
            ("Priority", priority_names.get(item.priority, str(item.priority))),
            ("Tags", ", ".join(item.tags) if item.tags else "None available"),
            ("Attachments", "Not exposed by Reminders AppleScript"),
            ("Created", item.creation_date or "Not available"),
            ("Modified", item.modification_date or "Not available"),
            ("Completed on", item.completion_date or "Not applicable"),
            ("Reminder ID", item.identifier or "Not available"),
        ]
        self._show_details("\n\n".join(f"{label}\n{value}" for label, value in rows))
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
