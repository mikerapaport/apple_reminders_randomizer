"""Qt desktop app for choosing a random active Apple Reminder."""
from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        print(
            "Qt UI dependency missing. Install the project requirements with:\n"
            "  python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    raise

from pdf_export import export_pdf
from reminders import Reminder, fetch_reminders

DEBUG = True


def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}", flush=True)


class ReminderLoader(QThread):
    title_loaded = Signal(str)
    batch_loaded = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reminders: list[Reminder] = []
        self.error: str | None = None
        self.elapsed = 0.0

    def run(self) -> None:
        started = time.perf_counter()
        debug_log("now loading open reminders")
        try:
            self.reminders = fetch_reminders(
                on_title_loaded=self._title_loaded,
                on_batch_loaded=self._batch_loaded,
                should_cancel=self.isInterruptionRequested,
            )
            self.elapsed = time.perf_counter() - started
            debug_log(f"Reminders responded in {self.elapsed:.1f}s")
            debug_log(f"loaded {len(self.reminders)} open reminders")
        except Exception as exc:
            self.error = str(exc)
            debug_log(f"reminder load failed: {self.error}")

    def _title_loaded(self, title: str) -> None:
        debug_log(f"loaded reminder title: {title}")
        self.title_loaded.emit(title)

    def _batch_loaded(self, list_name: str, count: int) -> None:
        debug_log(f"loaded batch: {count} active reminder(s) from list {list_name}")
        self.batch_loaded.emit(list_name, count)


class ReminderRandomizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Choose A Random Task")
        self.resize(900, 720)
        self.setMinimumSize(620, 500)
        self.reminders: list[Reminder] = []
        self.loader: ReminderLoader | None = None
        self.loaded_so_far = 0
        self._progress_value = 0
        self._progress_direction = 1
        self._build_ui()
        debug_log("application started")

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #202124; color: #f5f7fa; }
            QLabel { color: #f5f7fa; }
            QPushButton {
                background-color: #373a40; color: #f5f7fa; border: 0;
                border-radius: 8px; padding: 10px 16px; font-size: 14px;
            }
            QPushButton:hover { background-color: #454a52; }
            QPushButton:disabled { color: #858b95; background-color: #303237; }
            QProgressBar {
                background-color: #41454c; border: 0; border-radius: 6px;
                min-height: 18px; max-height: 18px;
            }
            QProgressBar::chunk { background-color: #78a9ff; border-radius: 6px; }
            QScrollArea { background: transparent; border: 0; }
        """)

        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        heading = QLabel("Choose A Random Task")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setStyleSheet("font-size: 26px; font-weight: 700;")
        outer.addWidget(heading)

        self.progress_status = QLabel("Starting automatic load…")
        self.progress_status.setTextFormat(Qt.TextFormat.PlainText)
        self.progress_status.setWordWrap(True)
        self.progress_status.setStyleSheet("font-size: 14px; color: #c7ccd4;")
        outer.addWidget(self.progress_status)

        # Drive the bar ourselves instead of relying on the platform's native
        # indeterminate animation, which was not visibly moving on this Mac.
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        outer.addWidget(self.progress)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(24)
        self.progress_timer.timeout.connect(self._advance_progress)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.display_panel = QWidget()
        self.display_panel.setStyleSheet(
            "background-color: #292b30; border: 1px solid #484d56; border-radius: 10px;"
        )
        self.display_layout = QVBoxLayout(self.display_panel)
        self.display_layout.setContentsMargins(24, 22, 24, 22)
        self.display_layout.setSpacing(14)

        self.display_title = self._plain_label("Loading active reminders", 22)
        self.display_layout.addWidget(self.display_title)
        self.display_source = self._plain_label(
            "Completed reminders are skipped. Your reminders will appear here as they load.", 14
        )
        self.display_source.setStyleSheet(
            "font-size: 17px; color: #c7ccd4; background: transparent; border: 0;"
        )
        self.display_layout.addWidget(self.display_source)

        self.metadata_panel = QWidget()
        self.metadata_panel.setStyleSheet("background: transparent; border: 0;")
        self.metadata_layout = QFormLayout(self.metadata_panel)
        self.metadata_layout.setContentsMargins(0, 10, 0, 0)
        self.metadata_layout.setHorizontalSpacing(20)
        self.metadata_layout.setVerticalSpacing(10)
        self.metadata_layout.setLabelAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.metadata_rows: dict[str, QLabel] = {}
        for key, caption in (
            ("notes", "Notes"),
            ("due", "Due"),
            ("status", "Status"),
            ("flagged", "Flagged"),
            ("priority", "Priority"),
            ("tags", "Tags"),
            ("attachments", "Attachments"),
        ):
            name = self._plain_label(caption, 13, True)
            name.setStyleSheet("color: #9dbfff; background: transparent; border: 0;")
            value = self._plain_label("", 14)
            value.setStyleSheet("background: transparent; border: 0;")
            self.metadata_layout.addRow(name, value)
            self.metadata_rows[key] = value
        self.metadata_panel.hide()
        self.display_layout.addWidget(self.metadata_panel)
        self.display_layout.addStretch(1)
        self.scroll.setWidget(self.display_panel)
        outer.addWidget(self.scroll, 1)

        self.actions = QWidget()
        action_row = QHBoxLayout(self.actions)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(10)
        self.refresh_button = QPushButton("Load / Refresh Reminders")
        self.pdf_button = QPushButton("Export PDF")
        self.json_button = QPushButton("Save JSON")
        for button in (self.refresh_button, self.pdf_button, self.json_button):
            action_row.addWidget(button)
        self.refresh_button.clicked.connect(self.load_reminders)
        self.pdf_button.clicked.connect(self.save_pdf)
        self.json_button.clicked.connect(self.save_json)
        self.actions.hide()
        outer.addWidget(self.actions)

        self.generate_button = QPushButton("Generate Task")
        self.generate_button.setStyleSheet(
            "background-color: #356fd2; color: white; font-size: 16px; "
            "font-weight: 700; padding: 13px;"
        )
        self.generate_button.clicked.connect(self.generate_task)
        self.generate_button.hide()
        outer.addWidget(self.generate_button)

        self.footer = QLabel("Connecting to Apple Reminders…")
        self.footer.setTextFormat(Qt.TextFormat.PlainText)
        self.footer.setStyleSheet("font-size: 12px; color: #c7ccd4;")
        outer.addWidget(self.footer)

    @staticmethod
    def _plain_label(text: str, size: int = 14, bold: bool = False) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        weight = "700" if bold else "400"
        label.setStyleSheet(
            f"font-size: {size}px; font-weight: {weight}; background: transparent; border: 0;"
        )
        return label

    def _advance_progress(self) -> None:
        self._progress_value += self._progress_direction * 2
        if self._progress_value >= 100:
            self._progress_value = 100
            self._progress_direction = -1
        elif self._progress_value <= 0:
            self._progress_value = 0
            self._progress_direction = 1
        self.progress.setValue(self._progress_value)

    def _set_display_message(self, title: str, detail: str) -> None:
        self.metadata_panel.hide()
        self.display_title.setText(title)
        self.display_title.setStyleSheet(
            "font-size: 22px; font-weight: 400; background: transparent; border: 0;"
        )
        self.display_source.setText(detail)

    def load_reminders(self) -> None:
        if self.loader and self.loader.isRunning():
            return
        debug_log("load / refresh requested")
        self.loaded_so_far = 0
        self.actions.hide()
        self.generate_button.hide()
        self.progress.show()
        self._progress_value = 0
        self._progress_direction = 1
        self.progress.setValue(0)
        self.progress_timer.start()
        self.progress_status.setText("Reading active reminders…")
        self.footer.setText("Waiting for Apple Reminders")
        self._set_display_message(
            "Loading active reminders",
            "Completed reminders are skipped. The most recently read reminder will appear here.",
        )
        self.loader = ReminderLoader(self)
        self.loader.title_loaded.connect(self._show_recent_title)
        self.loader.batch_loaded.connect(self._show_batch)
        self.loader.finished.connect(self._finish_loading)
        self.loader.start()

    def _show_batch(self, list_name: str, count: int) -> None:
        self.progress_status.setText(f"Reading {count} active reminders from {list_name}…")
        self.display_source.setText(f"Reading {count} reminders from list: {list_name}")

    def _show_recent_title(self, title: str) -> None:
        self.loaded_so_far += 1
        self.progress_status.setText(f"Loaded {self.loaded_so_far} active reminders")
        self.display_source.setText(f"Recently loaded: {title}")

    def _finish_loading(self) -> None:
        worker = self.loader
        if worker is None:
            return
        self.progress_timer.stop()
        self.progress.hide()
        if worker.error:
            self.progress_status.setText("Reminder load failed")
            self.footer.setText("Could not load reminders. Use Refresh to try again.")
            self._set_display_message("Could not load reminders", worker.error)
            self.actions.show()
            self.refresh_button.setEnabled(True)
            self.pdf_button.setEnabled(False)
            self.json_button.setEnabled(False)
            self.generate_button.hide()
            return

        self.reminders = worker.reminders
        count = len(self.reminders)
        self.progress_status.setText(f"Loaded {count} active reminders in {worker.elapsed:.1f} seconds")
        self.footer.setText("Choose Generate Task to display a random active reminder.")
        self._set_display_message(
            "Reminders loaded",
            f"{count} active reminders are ready. Choose Generate Task to display one with its source list.",
        )
        self.actions.show()
        self.refresh_button.setEnabled(True)
        self.pdf_button.setEnabled(bool(self.reminders))
        self.json_button.setEnabled(bool(self.reminders))
        self.generate_button.setVisible(bool(self.reminders))
        debug_log(f"reminder load completed; {count} active reminders available")

    def generate_task(self) -> None:
        debug_log("generate task requested")
        candidates = [r for r in self.reminders if not r.completed and r.title.strip()]
        if not candidates:
            self._set_display_message(
                "No active reminders available",
                "Refresh Reminders to read the current open tasks.",
            )
            self.footer.setText("No active reminders are available.")
            return

        debug_log("now choosing a reminder")
        item = random.choice(candidates)
        debug_log(f"chosen reminder title: {item.title} | source list: {item.list_name}")
        priority_names = {0: "None", 1: "Low", 5: "Medium", 9: "High"}
        values = {
            "notes": item.notes or "None",
            "due": item.due_date or "Not set",
            "status": "Open",
            "flagged": "Yes" if item.flagged else "No",
            "priority": priority_names.get(item.priority, str(item.priority)),
            "tags": ", ".join(item.tags) if item.tags else "None available",
            "attachments": "Not exposed by Reminders AppleScript",
        }
        self.display_title.setText(item.title)
        self.display_title.setStyleSheet(
            "font-size: 22px; font-weight: 700; background: transparent; border: 0;"
        )
        self.display_source.setText(f"Source list: {item.list_name or 'Unspecified'}")
        for key, value in values.items():
            self.metadata_rows[key].setText(str(value))
        self.metadata_panel.show()
        self.footer.setText(f"Picked from {item.list_name or 'Unspecified'} · {len(self.reminders)} active reminders")

    def save_pdf(self) -> None:
        if not self.reminders:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export reminders as PDF", "Apple Reminders.pdf", "PDF document (*.pdf)"
        )
        if not path:
            return
        try:
            debug_log("starting PDF export")
            export_pdf(self.reminders, path)
            self.footer.setText(f"PDF exported to {Path(path).name}")
            debug_log("PDF export completed")
        except Exception as exc:
            debug_log(f"PDF export failed: {exc}")
            QMessageBox.critical(self, "PDF export failed", str(exc))

    def save_json(self) -> None:
        if not self.reminders:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save reminder data", "Apple Reminders.json", "JSON file (*.json)"
        )
        if not path:
            return
        try:
            debug_log("starting JSON export")
            Path(path).write_text(
                json.dumps([asdict(item) for item in self.reminders], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.footer.setText(f"JSON saved to {Path(path).name}")
            debug_log("JSON export completed")
        except OSError as exc:
            debug_log(f"JSON export failed: {exc}")
            QMessageBox.critical(self, "JSON export failed", str(exc))

    def closeEvent(self, event) -> None:
        if self.loader and self.loader.isRunning():
            self.loader.requestInterruption()
            if not self.loader.wait(2500):
                event.ignore()
                self.footer.setText("Still waiting for Reminders to stop; try closing again shortly.")
                return
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = ReminderRandomizer()
    window.show()
    QTimer.singleShot(100, window.load_reminders)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
