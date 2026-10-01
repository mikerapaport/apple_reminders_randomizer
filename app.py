"""A small macOS desktop app for choosing a random Apple Reminder."""
from __future__ import annotations
import json
import random
import threading
import sys
import time
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

BG = "#202124"
PANEL = "#292b30"
INK = "#f5f7fa"
MUTED = "#c2c7d0"
ACCENT = "#75a7ff"
ACTION = "#356fd2"
PROGRESS_TRACK = "#4b505a"
DEBUG = True

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}", flush=True)

class ReminderRandomizer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Random Reminders")
        self.root.geometry("900x700")
        self.root.minsize(680, 520)
        self.root.configure(bg=BG)
        self.reminders: list[Reminder] = []
        self.current: Reminder | None = None
        self.generate_after_load = False
        self.loading = False
        self.loaded_so_far = 0
        self.status = tk.StringVar(value="Preparing to load open reminders…")
        self._build()
        debug_log("application started")

    def _build(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        outer = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(4, weight=1)

        tk.Label(outer, text="Random Reminders", bg=BG, fg=INK,
                 font=("Helvetica Neue", 25, "bold"), anchor="w").grid(
                     row=0, column=0, sticky="ew")
        toolbar = tk.Frame(outer, bg=BG)
        self.toolbar = toolbar
        toolbar.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        self.load_button = tk.Button(toolbar, text="Load / Refresh Reminders", command=self.load,
                                     padx=10, pady=5)
        self.load_button.pack(side="left")
        self.pdf_button = tk.Button(toolbar, text="Export PDF", command=self.save_pdf,
                                    padx=10, pady=5)
        self.pdf_button.pack(side="left", padx=(8, 0))
        self.json_button = tk.Button(toolbar, text="Save JSON", command=self.save_json,
                                     padx=10, pady=5)
        self.json_button.pack(side="left", padx=(8, 0))

        self.count = tk.StringVar(value="Starting automatic load…")
        tk.Label(outer, textvariable=self.count, bg=BG, fg=MUTED,
                 font=("Helvetica Neue", 10), anchor="w").grid(
                     row=2, column=0, sticky="ew", pady=(0, 5))

        self.progress_running = False
        self.progress_position = 0
        self.progress_canvas = tk.Canvas(outer, height=4, bg=BG,
                                         highlightthickness=0, borderwidth=0)
        self.progress_canvas.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        display = tk.Frame(outer, bg=PANEL, highlightbackground="#4b505a",
                           highlightthickness=1)
        display.grid(row=4, column=0, sticky="nsew")
        display.grid_rowconfigure(0, weight=1)
        display.grid_columnconfigure(0, weight=1)
        self.details = tk.Text(display, wrap="word", bg=PANEL, fg=INK,
                               insertbackground=INK, selectbackground="#456da9",
                               font=("Helvetica Neue", 12), relief="flat", borderwidth=0,
                               padx=22, pady=18, insertwidth=0, cursor="arrow", takefocus=False)
        self.details.grid(row=0, column=0, sticky="nsew")
        self.details.bind("<Key>", lambda _event: "break")
        self.details.bind("<<Paste>>", lambda _event: "break")
        self.details.bind("<<Cut>>", lambda _event: "break")
        scrollbar = tk.Scrollbar(display, orient="vertical", command=self.details.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.details.configure(yscrollcommand=scrollbar.set)
        self.details.tag_configure("task_title", font=("Helvetica Neue", 22, "bold"), foreground=INK)
        self.details.tag_configure("source", font=("Helvetica Neue", 13, "bold"), foreground=ACCENT)
        self._show_details("Loading active reminders automatically…\n\nCompleted reminders are skipped.")

        self.generate_button = tk.Button(outer, text="Generate Task", command=self.generate_task,
                                         bg=ACTION, fg="white", activebackground="#285ba8",
                                         activeforeground="white", font=("Helvetica Neue", 14, "bold"),
                                         relief="flat", padx=12, pady=11, cursor="pointinghand")
        self.generate_button.grid(row=5, column=0, sticky="ew", pady=(12, 7))
        tk.Label(outer, textvariable=self.status, bg=BG, fg=MUTED,
                 font=("Helvetica Neue", 10), anchor="w").grid(
                     row=6, column=0, sticky="ew")
        self._set_actions_visible(False)

    def _show_details(self, text: str):
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.yview_moveto(0)

    def _set_actions_visible(self, loaded: bool, failed: bool = False):
        if loaded:
            self.toolbar.grid()
            self.generate_button.grid()
            self.load_button.configure(state="normal")
            self.pdf_button.configure(state="normal")
            self.json_button.configure(state="normal")
        elif failed:
            self.toolbar.grid()
            self.generate_button.grid_remove()
            self.load_button.configure(state="normal")
            self.pdf_button.configure(state="disabled")
            self.json_button.configure(state="disabled")
        else:
            self.toolbar.grid_remove()
            self.generate_button.grid_remove()

    def _start_progress(self):
        self.progress_canvas.configure(height=18, bg=PROGRESS_TRACK)
        self.progress_running = True
        self.progress_position = 0
        self.progress_canvas.update_idletasks()
        self._animate_progress()

    def _animate_progress(self):
        if not self.progress_running:
            return
        width = self.progress_canvas.winfo_width()
        self.progress_canvas.delete("progress")
        height = max(12, self.progress_canvas.winfo_height())
        chunk = max(60, width // 3)
        self.progress_canvas.create_rectangle(0, 0, width, height,
                                              fill=PROGRESS_TRACK, outline="", tags="progress")
        left = self.progress_position % max(1, width + chunk) - chunk
        self.progress_canvas.create_rectangle(max(0, left), 0,
                                              min(width, left + chunk), height,
                                              fill=ACCENT, outline="", tags="progress")
        self.progress_position += 14
        self.root.after(30, self._animate_progress)

    def _stop_progress(self):
        self.progress_running = False
        self.progress_canvas.delete("progress")
        self.progress_canvas.configure(height=4, bg=BG)

    def load(self, generate_when_ready=False):
        if self.loading:
            self.generate_after_load = self.generate_after_load or generate_when_ready
            return
        self.loading = True
        self.generate_after_load = generate_when_ready
        self.loaded_so_far = 0
        self._set_actions_visible(False)
        self.count.set("Loading active reminders… 0 read")
        self._show_details("Reading active reminders. Completed reminders are skipped.")
        self.status.set("Reading reminders…")
        self._start_progress()
        self.root.update_idletasks()
        debug_log("now loading open reminders")
        threading.Thread(target=self._load_background, daemon=True).start()

    def _load_background(self):
        started = time.perf_counter()
        try:
            data = fetch_reminders(
                on_title_loaded=self._on_title_loaded,
                on_batch_loaded=self._on_batch_loaded,
            )
            debug_log(f"Reminders responded in {time.perf_counter() - started:.1f}s")
            debug_log(f"loaded {len(data)} open reminders")
            self.root.after(0, lambda: self._loaded(data))
        except RemindersAccessError as exc:
            debug_log(f"reminder load failed: {exc}")
            self.root.after(0, lambda detail=str(exc): self._load_failed(detail))
        except Exception as exc:
            detail = f"Unexpected error while reading Reminders: {exc}"
            debug_log(f"{detail}")
            self.root.after(0, lambda detail=detail: self._load_failed(detail))

    def _on_batch_loaded(self, list_name: str, count: int):
        debug_log(f"loaded batch: {count} active reminder(s) from list {list_name}")
        self.root.after(0, lambda: self._show_loading_batch(list_name, count))

    def _show_loading_batch(self, list_name: str, count: int):
        self._show_details(f"Loading active reminders…\n\nNow reading {count} reminders from “{list_name}”.")

    def _on_title_loaded(self, title: str):
        debug_log(f"loaded reminder title: {title}")
        self.root.after(0, lambda title=title: self._increment_loaded_count(title))

    def _increment_loaded_count(self, title: str):
        self.loaded_so_far += 1
        self.count.set(f"Loading active reminders… {self.loaded_so_far} read")
        self._show_details(f"Loading active reminders…\n\nRecently loaded: {title}")

    def _loaded(self, data):
        self.loading = False
        self._stop_progress()
        self.reminders = data
        self.current = None
        self.count.set(f"{len(data)} active reminders loaded")
        self.status.set("Active reminders loaded. Click Generate Task.")
        self._set_actions_visible(True)
        debug_log(f"reminder load completed; {len(data)} active reminders available")
        self._show_details("Reminder data loaded. Click Generate Task to choose one.")
        if self.generate_after_load:
            self.generate_after_load = False
            self.pick()

    def _load_failed(self, detail):
        self.loading = False
        self._stop_progress()
        self.generate_after_load = False
        self.count.set("Reminder load failed")
        self._show_details(f"Could not load reminders.\n\n{detail}")
        self.status.set("Could not load reminders.")
        self._set_actions_visible(False, failed=True)
        messagebox.showerror("Can't read Reminders", detail, parent=self.root)

    def generate_task(self):
        debug_log("generate task requested")
        if not self.reminders:
            self.load(generate_when_ready=True)
            return
        self.pick()

    def pick(self):
        debug_log("now choosing a reminder")
        pool = [r for r in self.reminders if not r.completed and r.title.strip()]
        if not pool:
            debug_log("no active reminders are available to choose")
            messagebox.showinfo("No tasks available", "No active reminders are loaded. Refresh Reminders and try again.", parent=self.root)
            return
        self.current = random.choice(pool)
        item = self.current
        debug_log(f"chosen reminder title: {item.title} | source list: {item.list_name}")
        priority_names = {0: "None", 1: "Low", 5: "Medium", 9: "High"}
        rows = [
            ("Notes", item.notes or "None"),
            ("Due", item.due_date or "Not set"),
            ("Status", "Open"),
            ("Flagged", "Yes" if item.flagged else "No"),
            ("Priority", priority_names.get(item.priority, str(item.priority))),
            ("Tags", ", ".join(item.tags) if item.tags else "None available"),
            ("Attachments", "Not exposed by Reminders AppleScript"),
            ("Created", item.creation_date or "Not available"),
            ("Modified", item.modification_date or "Not available"),
            ("Completed on", item.completion_date or "Not applicable"),
            ("Reminder ID", item.identifier or "Not available"),
        ]
        self.details.delete("1.0", "end")
        self.details.insert("end", item.title + "\n", "task_title")
        self.details.insert("end", f"Source list: {item.list_name or 'Unspecified'}\n\n", "source")
        self.details.insert("end", "\n\n".join(f"{label}\n{value}" for label, value in rows))
        self.details.yview_moveto(0)
        self.status.set(f"Picked from {item.list_name} · {len(pool)} eligible reminder{'s' if len(pool) != 1 else ''}.")
        self.root.update_idletasks()

    def save_pdf(self):
        if not self.reminders:
            messagebox.showinfo("Nothing to export", "Load reminders first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export reminders as PDF", defaultextension=".pdf", filetypes=[("PDF document", "*.pdf")], initialfile="Apple Reminders.pdf")
        if not path: return
        try:
            debug_log("starting PDF export")
            export_pdf(self.reminders, path)
            self.status.set(f"PDF exported to {Path(path).name}")
            debug_log("PDF export completed")
        except Exception as exc:
            debug_log(f"PDF export failed: {exc}")
            messagebox.showerror("PDF export failed", str(exc), parent=self.root)

    def save_json(self):
        if not self.reminders:
            messagebox.showinfo("Nothing to export", "Load reminders first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Save reminder data", defaultextension=".json", filetypes=[("JSON file", "*.json")], initialfile="Apple Reminders.json")
        if not path: return
        try:
            debug_log("starting JSON export")
            Path(path).write_text(json.dumps([asdict(r) for r in self.reminders], ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set(f"JSON saved to {Path(path).name}")
            debug_log("JSON export completed")
        except OSError as exc:
            debug_log(f"JSON export failed: {exc}")
            messagebox.showerror("JSON export failed", str(exc), parent=self.root)

def main():
    root = tk.Tk()
    app = ReminderRandomizer(root)
    root.after(150, app.load)
    root.mainloop()

if __name__ == "__main__":
    main()
