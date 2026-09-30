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
      set listTitle to name of reminderList
      repeat with reminderItem in (every reminder of reminderList)
        set itemTitle to name of reminderItem
        set itemNotes to body of reminderItem
        set itemId to id of reminderItem
        set itemDone to completed of reminderItem
        set itemFlagged to flagged of reminderItem
        set itemPriority to priority of reminderItem
        set itemDue to ""
        set itemCreated to ""
        set itemModified to ""
        set itemCompletedAt to ""
        try
          set itemDue to (due date of reminderItem) as «class isot»
        end try
        try
          set itemCreated to (creation date of reminderItem) as «class isot»
        end try
        try
          set itemModified to (modification date of reminderItem) as «class isot»
        end try
        try
          set itemCompletedAt to (completion date of reminderItem) as «class isot»
        end try
        if not isFirst then set outputText to outputText & ","
        set isFirst to false
        set outputText to outputText & "{" & ¬
          "\"title\":" & my quoteJSON(itemTitle) & "," & ¬
          "\"notes\":" & my quoteJSON(itemNotes) & "," & ¬
          "\"list_name\":" & my quoteJSON(listTitle) & "," & ¬
          "\"due_date\":" & my quoteJSON(itemDue) & "," & ¬
          "\"flagged\":" & (itemFlagged as string) & "," & ¬
          "\"completed\":" & (itemDone as string) & "," & ¬
          "\"priority\":" & (itemPriority as string) & "," & ¬
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
        raise RemindersAccessError("Reminders returned data the app could not read.") from exc
    return [Reminder(
        title=row.get("title", ""), notes=row.get("notes", "") or "",
        list_name=row.get("list_name", ""), due_date=row.get("due_date", "") or "",
        flagged=row.get("flagged") is True, completed=row.get("completed") is True,
        priority=int(row.get("priority") or 0), creation_date=row.get("creation_date", "") or "",
        modification_date=row.get("modification_date", "") or "",
        completion_date=row.get("completion_date", "") or "", tags=tuple(row.get("tags") or ()),
        identifier=row.get("identifier", "")) for row in records]

def reminder_as_dict(reminder: Reminder) -> dict:
    return asdict(reminder)
