"""Minimal MCP server over stdio (no dependencies) for the context-capture probe."""
import json
import sys


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        req = json.loads(line)
    except Exception:
        continue
    method, rid = req.get("method"), req.get("id")
    if rid is None:
        continue  # notifications need no reply
    if method == "initialize":
        version = (req.get("params") or {}).get("protocolVersion", "2025-06-18")
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "unpack-probe", "version": "0.1.0"},
            "instructions": "PROBE-MCP-INSTRUCTIONS: the unpack-probe server returns a fixed marker.",
        }})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [{
            "name": "probe_echo",
            "description": "PROBE-MCP-TOOL-DESCRIPTION: returns a fixed marker string.",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
        }]}})
    elif method == "tools/call":
        text = ((req.get("params") or {}).get("arguments") or {}).get("text", "")
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": f"PROBE-MCP-RESULT: echo={text}"}]}})
    else:
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
