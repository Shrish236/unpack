# CLI and pre-push hook

Status: **built** on `main` (`7ad132c`), in `cli/`. Source of the design: [session pipeline §3](session-pipeline.md#3-the-pre-push-hook), [server design §5.1](server-design.md#51-post-v1ingest-cli-hook), and the [product plan](product-plan.md#41-cli-and-hook-developers-machine).

## 1. Purpose

On `git push`, the CLI:

1. works out which commits are being pushed;
2. finds the agent session that produced them (Gemini CLI first);
3. trims the session so the server parser stays simple;
4. removes secrets from everything it will send;
5. sends one payload to the Unpack server, in the background, with a short timeout.

The hook **never blocks the push**. Any failure prints one `Unpack warning:` line to stderr and exits 0.

## 2. Commands

| Command | What it does |
|---|---|
| `unpack install --server URL [--token T] [--default-branch B] [--timeout S]` | Installs `.git/hooks/pre-push` (backing up any existing hook as `pre-push.unpack-orig`) and saves the repository's config |
| `unpack uninstall` | Removes the hook and restores the backup |
| `unpack push [--base SHA] [--head SHA] [--server URL] [--token T] [--default-branch B] [--timeout S] [--dry-run[=PATH]]` | Builds the payload for HEAD and sends it, or with `--dry-run` writes the redacted payload to a file (default `.unpack-dry-run.json`, or `-` for stdout) without sending. Use it to resend a push or to review what would leave the machine |
| `unpack status` | Shows hook, config and session status |
| `unpack hook …` | The entry point git calls. Reads `<ref> <sha> <ref> <sha>` lines on stdin |
| `unpack mock-server [--host H] [--port P] [--out-dir D]` | Starts a local mock `/ingest` server for end-to-end tests (`cli/mock_server.py`) |

## 3. Modules

| File | Responsibility |
|---|---|
| `cli/main.py` | Argument parsing and the subcommands |
| `cli/hook.py` | Hook install, uninstall and status; `parse_pre_push_refs`; `build_push_payload`; `run_pre_push_hook` |
| `cli/git_info.py` | Git plumbing: repository root, remote parsing, default branch, base and head SHA, commits, unified diff, changed files and their contents (1 MB limit, binary detection) |
| `cli/session_finder.py` | Finds the newest Gemini CLI session for this repository, trims it (see §5) |
| `cli/secrets.py` | `SecretScanner`: exact values from `.env` files and sensitive environment variables, known token patterns, and high-entropy assignments |
| `cli/transport.py` | Builds the ingest payload and POSTs it as gzipped JSON |
| `cli/config.py` | Per-repository config file: server URL, token, timeout, default branch |
| `cli/mock_server.py` | Local stand-in for `/v1/ingest` |
| `cli/__main__.py` | Lets `python -m cli` run the same entry point |

## 4. Choosing the commits

Git passes `<local ref> <local sha> <remote ref> <remote sha>` lines on stdin.

- `head_sha` is the local sha. Deletes (local sha all zeros) are skipped.
- `base_sha` is the remote sha when the branch already exists on the remote. Otherwise it is the merge base of `HEAD` and `origin/<default branch>`.
- One payload is sent per branch pushed. Tags are skipped.

## 5. Finding and trimming the session

**Finding.** The repository root is looked up in `~/.gemini/projects.json` to get the short project ID. If there is no entry, the SHA-256 of the root path is used. The newest `session-*.jsonl` under `~/.gemini/tmp/<id>/chats/` whose last update is after the parent of the oldest pushed commit is selected. If none matches, the payload is sent with `session: null`, and the server marks every change as `outside_session`.

**Trimming (client side, light).** The server does the real work; the CLI keeps the session's shape intact:

- drop `tokens` from every message;
- drop `displayContent`, `displayName` and `renderOutputAsMarkdown`;
- cap each tool call's result, and any string `resultDisplay`, at 20 KB, keeping the head and tail with a `…[truncated N bytes]…` marker;
- keep `FileDiff.originalContent` and `newContent` in full, because matching depends on them, and keep `args`, `thoughts` and `content` unchanged.

## 6. Removing secrets

Redaction runs over **every string** sent: the diff, each file's base and head content, and every session line.

1. **Exact values** from the repository's `.env*` files (values of 6 characters or more), and from environment variables whose names contain `KEY`, `TOKEN`, `SECRET` or `PASSWORD` (values of 8 characters or more). Trivial values, such as `true` or `localhost`, are ignored.
2. **Patterns:** AWS keys, GitHub tokens (`ghp_`, `github_pat_`, `gho_` and others), Google API keys (`AIza…`), OpenAI and Anthropic keys, Slack tokens, Stripe keys, private key blocks, JWTs, `password=` and `secret=` assignments, and connection strings with credentials.
3. **High-entropy strings** of 32 or more characters in assignments.

Matches become `[REDACTED:<type>]`. The payload carries counts per type (for example `{"env_value": 2, "github_token": 1}`), never the values.

## 7. The payload

`POST {server}/v1/ingest`, `Content-Type: application/json`, `Content-Encoding: gzip`, `Authorization: Bearer <repo ingest token>` (the token can be omitted for a localhost server). Full field rules are in [server design §5.1](server-design.md#51-post-v1ingest-cli-hook). The main fields:

```json
{
  "schema_version": 1,
  "repo": {"remote_url": "...", "owner": "...", "name": "...", "default_branch": "main"},
  "branch": "feature/retries",
  "base_sha": "40 hex", "head_sha": "40 hex",
  "commits": [{"sha": "...", "message": "...", "author_time": "..."}],
  "diff": "unified diff base..head, -U3",
  "changed_files": [{"path": "...", "old_path": null, "status": "M", "is_binary": false,
                     "base_content": "...", "head_content": "...", "truncated": false}],
  "session": {"agent": "gemini-cli", "agent_version": null,
              "file_name": "session-....jsonl", "lines": []},
  "redactions": {"env_value": 2},
  "client": {"cli_version": "0.1.0", "os": "linux", "hook": "pre-push"}
}
```

**Why `base_content` and `head_content` are sent.** The hook runs before the push reaches GitHub, so the server cannot yet fetch `head_sha`. Sending the changed files makes analysis independent of timing. The server still keeps a clone for the full graph (see [server design §3](server-design.md#3-linking-pushes-to-prs-track-the-branch-reconcile-on-a-timer)).

**Size.** A file over 1 MB is sent as `null` with `truncated: true`. Binary files are listed without contents. The server rejects payloads over 25 MB compressed or 150 MB uncompressed.

**Timeout.** The send uses the configured timeout (5 s by default). A failed send prints one warning and the push continues.

## 8. Behaviour on failure

| Case | Result |
|---|---|
| Server or database down | One warning; push succeeds; nothing analysed. Resend later with `unpack push` |
| No session found | Sent with `session: null`; analysis marks all changes `outside_session` |
| Hook run outside a repository, or on a branch deletion | Skipped |
| Unexpected exception | One warning; exit 0 |

## 9. Gaps against the design

- **Commit trailers** are not written. Deferred by design.
- **Only Gemini CLI** is read. Other adapters are later work.
- **Verification of the session format.** The format comes from the Gemini CLI source (commit `808199f`, 19 Nov 2026). Confirm against three real sessions from the installed Gemini CLI version before the demo (see [session pipeline §6](session-pipeline.md#6-build-order-and-checks)).
- **Dry run** (`unpack push --dry-run`) is implemented and is the way to review redaction by eye before the demo.
