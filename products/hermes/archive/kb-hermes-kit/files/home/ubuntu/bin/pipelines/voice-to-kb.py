#!/usr/bin/env python3
"""
Голосовая заметка → kb/fleeting/ → git commit → push.

Вход: текст транскрипции (stdin или аргумент).
Выход: файл в kb, коммит, пуш. Результат в stdout для агента.

Использование:
    echo "текст заметки" | python3 voice-to-kb.py
    python3 voice-to-kb.py "текст заметки"
    python3 voice-to-kb.py --file /path/to/transcript.txt
"""

import os
import subprocess
import sys
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

KB_PATH = os.path.expanduser("~/src/github.com/afpsy/kb")
DEFAULT_TIMEZONE = "Europe/Moscow"


def make_title(text):
    """Короткое название из первых слов."""
    first = text.split(".")[0].split("\n")[0].strip()
    if len(first) > 70:
        first = first[:70].rsplit(" ", 1)[0]
    return first


def resolve_timezone():
    """Prefer Hermes timezone config; fallback to system local timezone, then MSK."""
    config_path = os.path.expanduser("~/.hermes/config.yaml")
    try:
        with open(config_path) as f:
            for line in f:
                if line.startswith("timezone:"):
                    name = line.split(":", 1)[1].strip().strip("'\"")
                    if name:
                        return ZoneInfo(name)
    except OSError:
        pass
    except ZoneInfoNotFoundError:
        pass

    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is not None:
        return local_tz

    return ZoneInfo(DEFAULT_TIMEZONE)


def save_note(text, title):
    now = datetime.now(resolve_timezone())
    date_str = now.strftime("%Y-%m-%d %H:%M")
    filename = f"{date_str} {title}.md"
    filepath = os.path.join(KB_PATH, "fleeting", filename)

    note_id = str(uuid.uuid1())
    content = f'''---
type: note
id: "{note_id}"
title: "{title}"
date: {now.strftime("%Y-%m-%d")}
timestamp: {now.isoformat()}
source: voice
ingest_status: draft
---

{text}
'''
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


def git_commit_push(filepath):
    os.chdir(KB_PATH)
    rel = os.path.relpath(filepath, KB_PATH)
    subprocess.run(["git", "add", rel], check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"voice: {os.path.basename(filepath)}"],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "pull", "--rebase"], check=True, capture_output=True)
    subprocess.run(["git", "push"], check=True, capture_output=True)
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip()


def main():
    # --- прочитать текст ---
    text = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            text = f.read().strip()
    elif len(sys.argv) >= 2 and sys.argv[1] != "--file":
        text = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text:
        print("Usage: voice-to-kb.py <text>  |  --file <path>  |  stdin", file=sys.stderr)
        sys.exit(1)

    title = make_title(text)

    try:
        filepath = save_note(text, title)
        commit = git_commit_push(filepath)
        print(f"OK: {commit}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
