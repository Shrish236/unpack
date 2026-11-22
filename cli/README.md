# unpack CLI

The developer-side tool. It installs a git `pre-push` hook; on every push it finds the agent session for the branch, removes secrets locally, and uploads the session and diff to an Unpack server.

```bash
pip install -e .          # from the repository root; provides the `unpack` command
```

## Commands

| Command | What it does |
|---|---|
| `unpack install --server URL --token TOKEN` | Installs the pre-push hook in the current repository and saves the server URL and ingest token. The token is optional for `localhost`. |
| `unpack uninstall` | Removes the hook and the saved config. |
| `unpack status` | Shows the config and the agent sessions the CLI can see. |
| `unpack push [--dry-run]` | Runs the same upload the hook runs. `--dry-run` prints what would be sent and sends nothing. |
| `unpack hook` | Entry point the git hook calls. You do not run it yourself. |
| `unpack mock-server` | A tiny local server that accepts uploads, for trying the CLI without the real server. |

## What is sent

1. The commits being pushed, the diff and the list of changed files (`git_info.py`).
2. The agent session for the branch, trimmed to the turns that matter (`session_finder.py`).
3. Nothing else. Before sending, `secrets.py` removes secrets using the values in your `.env` files, known token patterns and an entropy check.

The upload is gzip-compressed and authenticated with a per-repository bearer token (`Authorization: Bearer unp_...`). The hook never blocks a push: if anything fails, the push goes ahead and the failure is printed.

## Supported agents

| Agent | How |
|---|---|
| Gemini CLI | Read directly from `~/.gemini/tmp/`. |
| Antigravity CLI | Read by `agy_session.py`. |
| Claude Code | Converted to the Gemini session format by `adapters/claude_code.py`. Only `.py` files get full contents, because the code graph is Python only. |

The server reads one session format, so anything agent-specific stays in this directory.

## Layout

```
cli/
├── main.py            # argument parsing and commands
├── hook.py            # the pre-push hook runner
├── config.py          # saved server URL and token
├── git_info.py        # commits, diff, changed files
├── session_finder.py  # finds and trims the Gemini CLI session
├── agy_session.py     # Antigravity sessions
├── adapters/          # converters for other agents (Claude Code)
├── secrets.py         # local secret scrubbing
├── transport.py       # gzip upload
└── mock_server.py     # local stand-in server
```

Design details: [docs/cli-hook.md](../docs/cli-hook.md).
