"""Read Apple Reminders through macOS's built-in AppleScript support."""
from __future__ import annotations
import json
import subprocess
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
      repeat with reminderProperties in reminderPropertiesList
        set itemTitle to my safeString(name of reminderProperties)
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

def fetch_reminders() -> list[Reminder]:
    """Return reminders, including completed items, from all Reminders lists."""
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", _SCRIPT], capture_output=True, text=True, timeout=120, check=False)
    except FileNotFoundError as exc:
        raise RemindersAccessError("This app can read Reminders only on macOS.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RemindersAccessError("Reminders took too long to respond. Try again.") from exc
    if result.returncode:
        detail = result.stderr.strip() or "AppleScript could not read Reminders."
        if "-1743" in detail:
            detail += " Allow access in System Settings → Privacy & Security → Reminders."
        raise RemindersAccessError(detail)
    try:
        records = json.loads(result.stdout)
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

def reminder_as_dict(reminder: Reminder) -> dict:
    return asdict(reminder)
