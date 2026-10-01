# Random Reminders for macOS

A small Python desktop app that reads reminders from the macOS Reminders app, keeps the reminder fields as Python objects, and chooses an open task at random. It can also create a PDF snapshot or save the loaded reminder data as JSON.

## Run

1. Use Python 3.9 or newer on macOS 12 or newer, then open Terminal in this folder. This app uses PySide6 (Qt) for its desktop UI, not Tkinter.
2. Create a virtual environment and install the app dependencies:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   ```
3. Start the app. It automatically begins loading active reminders:

   ```sh
   python3 app.py
   ```
   macOS may ask you to allow access to Reminders. If permission was denied, change it in **System Settings → Privacy & Security → Reminders**.

## Reminder data

The app reads only active, incomplete reminders. It reads title, notes, list, due date, flagged state, priority, creation/modification dates, and the Reminders identifier. Debug logging is on by default; it prints action messages and reminder titles to the Terminal, never notes or other reminder metadata. Set `DEBUG = False` near the top of `app.py` to turn it off.

AppleScript's Reminders dictionary does not expose every newer Reminders feature consistently. In particular, tags and subtasks are not currently read by this version; tags are retained as an empty field. PDF is an output snapshot, not an import format. The JSON export retains all fields this version can read.

## Build a standalone app

After installing dependencies, you can package the app with PyInstaller:

```sh
pip install pyinstaller
pyinstaller --windowed --name "Random Reminders" app.py
```

The first launch of a packaged app may trigger a separate macOS Reminders permission prompt.
