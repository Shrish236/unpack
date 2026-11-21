"""Probe hook: logs every hook event it receives and injects a marker where the event allows context.

Never blocks: always exits 0. The log goes to /tmp so it never dirties the repository.
"""
import json
import os
import sys
import time

CONTEXT_EVENTS = {"SessionStart", "UserPromptSubmit", "PostToolUse"}

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
event = data.get("hook_event_name", "unknown")
try:
    os.makedirs("/tmp/unpack-probe", exist_ok=True)
    with open("/tmp/unpack-probe/hooks.log", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.time(), "event": event, "keys": sorted(data),
                             "tool": data.get("tool_name"), "transcript_path": data.get("transcript_path")}) + "\n")
except Exception:
    pass
if event in CONTEXT_EVENTS:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": f"PROBE-HOOK-{event}: injected by probe_hook.py"}}))
sys.exit(0)
