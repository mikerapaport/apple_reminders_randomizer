# Random Reminders for macOS

A small Python desktop app that reads reminders from the macOS Reminders app, keeps the reminder fields as Python objects, and chooses an open task at random. It can also create a PDF snapshot or save the loaded reminder data as JSON.

## Run

1. Install Python 3.10 or newer and open Terminal in this folder. Tkinter must be included with that Python. For Homebrew Python 3.9, install its Tkinter package first:

   ```sh
   brew install python-tk@3.9
   ```

   If Homebrew reports that Python 3.9 needs an upgrade, run `brew upgrade python@3.9` and use the resulting Homebrew `python3` to launch the app.

2. Create a virtual environment and install the PDF dependency:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   ```
3. Confirm Tkinter is available, then start the app:

   ```sh
   python3 -c 'import tkinter; print(tkinter.TkVersion)'
   python3 app.py
   ```
4. Click **Load from Reminders**. macOS may ask you to allow access to Reminders. If permission was denied, change it in **System Settings → Privacy & Security → Reminders**.

## Reminder data

The app reads title, notes, list, due date, completion state/date, flagged state, priority, creation/modification dates, and the Reminders identifier. It includes completed tasks in the loaded data, but excludes them from random picks unless **Include completed** is enabled.

AppleScript's Reminders dictionary does not expose every newer Reminders feature consistently. In particular, tags and subtasks are not currently read by this version; tags are retained as an empty field. PDF is an output snapshot, not an import format. The JSON export retains all fields this version can read.

## Build a standalone app

After installing dependencies, you can package the app with PyInstaller:

```sh
pip install pyinstaller
pyinstaller --windowed --name "Random Reminders" app.py
```

The first launch of a packaged app may trigger a separate macOS Reminders permission prompt.
