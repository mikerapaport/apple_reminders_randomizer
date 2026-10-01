"""Read Apple Reminders through macOS's built-in AppleScript support."""
from __future__ import annotations
import json
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class Reminder:
    title: str
    notes: str = ""
    list_name: str = ""
    due_date: str = ""
    flagged: bool = False
    completed: bool = False
    priority: int = 0
    creation_date: str = ""
    modification_date: str = ""
    completion_date: str = ""
    tags: tuple[str, ...] = ()
    identifier: str = ""

# Output is JSON so notes (including punctuation and line breaks) survive intact.
_SCRIPT = r'''on run
  set outputText to "["
  set isFirst to true
  tell application "Reminders"
    repeat with reminderList in lists
      set listTitle to my safeString(name of reminderList)
      -- Bulk-fetch property records for open reminders in this list. AppleScript's
      -- every-object property form returns a list of values in one Apple Event.
      set reminderPropertiesList to properties of (every reminder of reminderList whose completed is false)
      log "RR_BATCH:" & listTitle & "|" & ((count of reminderPropertiesList) as text)
      repeat with reminderProperties in reminderPropertiesList
        set itemTitle to my safeString(name of reminderProperties)
        log "RR_TITLE:" & my oneLine(itemTitle)
        set itemNotes to my safeString(body of reminderProperties)
        set itemId to my safeString(id of reminderProperties)
        set itemDone to my safeString(completed of reminderProperties)
        set itemFlagged to my safeString(flagged of reminderProperties)
        set itemPriority to my safeString(priority of reminderProperties)
        set itemDue to my safeString(due date of reminderProperties)
        set itemCreated to my safeString(creation date of reminderProperties)
        set itemModified to my safeString(modification date of reminderProperties)
        set itemCompletedAt to my safeString(completion date of reminderProperties)
        if not isFirst then set outputText to outputText & ","
        set isFirst to false
        set outputText to outputText & "{" & ¬
          "\"title\":" & my quoteJSON(itemTitle) & "," & ¬
          "\"notes\":" & my quoteJSON(itemNotes) & "," & ¬
          "\"list_name\":" & my quoteJSON(listTitle) & "," & ¬
          "\"due_date\":" & my quoteJSON(itemDue) & "," & ¬
          "\"flagged\":" & my quoteJSON(itemFlagged) & "," & ¬
          "\"completed\":" & my quoteJSON(itemDone) & "," & ¬
          "\"priority\":" & my quoteJSON(itemPriority) & "," & ¬
          "\"creation_date\":" & my quoteJSON(itemCreated) & "," & ¬
          "\"modification_date\":" & my quoteJSON(itemModified) & "," & ¬
          "\"completion_date\":" & my quoteJSON(itemCompletedAt) & "," & ¬
          "\"tags\":[]," & ¬
          "\"identifier\":" & my quoteJSON(itemId) & "}"
      end repeat
    end repeat
  end tell
  return outputText & "]"
end run

on safeString(valueToConvert)
  if valueToConvert is missing value then return ""
  try
    return valueToConvert as text
  on error
    try
      set dateValue to valueToConvert as date
      return dateValue as text
    on error
      return ""
    end try
  end try
end safeString

on oneLine(valueText)
  set savedDelimiters to AppleScript's text item delimiters
  set AppleScript's text item delimiters to {return, linefeed}
  set textPieces to text items of valueText
  set AppleScript's text item delimiters to " "
  set valueText to textPieces as text
  set AppleScript's text item delimiters to savedDelimiters
  return valueText
end oneLine

on quoteJSON(valueText)
  if valueText is missing value then set valueText to ""
  set valueText to valueText as text
  set AppleScript's text item delimiters to "\\"
  set pieces to text items of valueText
  set AppleScript's text item delimiters to "\\\\"
  set valueText to pieces as text
  set AppleScript's text item delimiters to "\""
  set pieces to text items of valueText
  set AppleScript's text item delimiters to "\\\""
  set valueText to pieces as text
  set AppleScript's text item delimiters to return
  set pieces to text items of valueText
  set AppleScript's text item delimiters to "\\n"
  set valueText to pieces as text
  set AppleScript's text item delimiters to linefeed
  set pieces to text items of valueText
  set AppleScript's text item delimiters to "\\n"
  set valueText to pieces as text
  set AppleScript's text item delimiters to tab
  set pieces to text items of valueText
  set AppleScript's text item delimiters to "\\t"
  set valueText to pieces as text
  set AppleScript's text item delimiters to ""
  return "\"" & valueText & "\""
end quoteJSON
'''

class RemindersAccessError(RuntimeError):
    pass

def fetch_reminders(on_title_loaded=None, on_batch_loaded=None) -> list[Reminder]:
    """Return reminders, including completed items, from all Reminders lists."""
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as output_file:
            process = subprocess.Popen(
                ["/usr/bin/osascript", "-e", _SCRIPT],
                stdout=output_file, stderr=subprocess.PIPE, text=True, bufsize=1,
            )
            stderr_queue = queue.Queue()

            def read_stderr():
                try:
                    for line in process.stderr:
                        stderr_queue.put(line)
                finally:
                    stderr_queue.put(None)

            reader = threading.Thread(target=read_stderr, daemon=True)
            reader.start()
            stderr_lines = []
            stderr_finished = False
            started = time.monotonic()
            while process.poll() is None or not stderr_finished:
                try:
                    line = stderr_queue.get(timeout=0.1)
                except queue.Empty:
                    line = ""
                if line is None:
                    stderr_finished = True
                elif line:
                    batch = _script_log_payload(line, "RR_BATCH:")
                    title = _script_log_payload(line, "RR_TITLE:")
                    if batch is not None:
                        list_name, separator, batch_count = batch.rpartition("|")
                        if separator and on_batch_loaded:
                            try:
                                on_batch_loaded(list_name, int(batch_count))
                            except (TypeError, ValueError):
                                pass
                    elif title is not None:
                        if on_title_loaded:
                            on_title_loaded(title)
                    else:
                        stderr_lines.append(line)
                if process.poll() is None and time.monotonic() - started > 120:
                    process.kill()
                    process.wait()
                    reader.join(timeout=1)
                    raise RemindersAccessError("Reminders took too long to respond after 120 seconds. Try again.")
            return_code = process.wait()
            reader.join(timeout=1)
            output_file.seek(0)
            stdout = output_file.read()
    except FileNotFoundError as exc:
        raise RemindersAccessError("This app can read Reminders only on macOS.") from exc
    if return_code:
        detail = "".join(stderr_lines).strip() or "AppleScript could not read Reminders."
        if "-1743" in detail:
            detail += " Allow access in System Settings → Privacy & Security → Reminders."
        raise RemindersAccessError(detail)
    try:
        records = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RemindersAccessError(
            f"Reminders returned invalid JSON at line {exc.lineno}, column {exc.colno}. "
            "The raw reminder contents were not printed because they may contain private notes."
        ) from exc
    if not isinstance(records, list):
        raise RemindersAccessError("Reminders returned data in an unexpected format (expected a list).")

    def as_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "1"}

    def as_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    reminders = []
    for index, row in enumerate(records, start=1):
        if not isinstance(row, dict):
            raise RemindersAccessError(f"Reminder record {index} was not a text property record.")
        reminders.append(Reminder(
            title=str(row.get("title", "") or ""), notes=str(row.get("notes", "") or ""),
            list_name=str(row.get("list_name", "") or ""), due_date=str(row.get("due_date", "") or ""),
            flagged=as_bool(row.get("flagged")), completed=as_bool(row.get("completed")),
            priority=as_int(row.get("priority")), creation_date=str(row.get("creation_date", "") or ""),
            modification_date=str(row.get("modification_date", "") or ""),
            completion_date=str(row.get("completion_date", "") or ""),
            tags=tuple(str(tag) for tag in (row.get("tags") or ())),
            identifier=str(row.get("identifier", "") or "")))
    return reminders


def _script_log_payload(line: str, marker: str):
    marker_at = line.find(marker)
    if marker_at < 0:
        return None
    payload = line[marker_at + len(marker):]
    wrapper_end = payload.rfind("*)")
    if wrapper_end >= 0:
        payload = payload[:wrapper_end]
    return payload.strip()

def reminder_as_dict(reminder: Reminder) -> dict:
    return asdict(reminder)
