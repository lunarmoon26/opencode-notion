# OpenCode Notion

One native OpenCode tool for managing your Notion workspace, backed by
[MCPorter](https://github.com/openclaw/mcporter) and the
[official hosted Notion MCP](https://developers.notion.com/guides/mcp/get-started-with-mcp).

Follows the single-tool + bundled-config + focused-skills pattern in
`lunarmoon26/opencode-xcode`. Uses the **OpenCode V2** plugin API
(`@opencode/plugin`), rather than the older API used in that project.
No new MCP server, integration token or separate infrastructure is needed.

## Start here

Requires Node.js 24+, Bun, and OpenCode V2. Python 3.10+ is needed for skill extraction and Markdown exports.

```sh
cd /path/to/opencode-notion
bun install --frozen-lockfile
bun run auth
```

Select the intended Notion workspace in the browser and authorize it. For a
headless host, `bun run auth:headless` prints a URL instead of opening a browser;
the browser must be able to reach the printed loopback callback (use SSH port
forwarding if the browser runs on another machine). Do not paste tokens into chat.

Then verify the connection without changing any workspace content:

```sh
bun run mcp -- list notion --schema --no-oauth
bun run mcp -- call notion.notion-get-self --args '{}' --output json --no-oauth
bun run mcp -- resource notion --json --no-oauth
```

Launch `opencode` **inside this project**. Its `opencode.json` loads the plugin,
skills and write-permission rule. No global configuration is changed.

Try:

> Verify my Notion workspace, then show my main pages and task databases. Read only.

> Find my project tracker and show overdue tasks. Fetch its schema first.

> Save this conversation as a decision record under [page URL].

> Find the Skill I use for weekly reviews; download its supporting files if needed.

Signing in does not edit Notion. The plugin requests `notion.write` permission
before mutations or new/unclassified tools. Keep that action set to `ask`.
Deletion, bulk moves and schema changes also require a clearly scoped user request.
This is a client-side approval policy, not a read-only OAuth grant or sandbox:
direct MCP/API calls outside the plugin are not covered by it.

## Use from other projects

Keep this checkout and its installed dependencies. Merge these fields into the
target project's OpenCode V2 configuration, using **absolute paths**:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["/absolute/path/opencode-notion/plugin/notion.ts"],
  "skills": ["/absolute/path/opencode-notion/skills"],
  "permissions": [
    { "action": "notion.write", "resource": "*", "effect": "ask" }
  ]
}
```

Preserve existing configuration and place the permission rule after broader
allow rules. Use the global config only if you want Notion in every project.
Don't register a second direct Notion MCP connection alongside this plugin unless
you intentionally want duplicate tools and a separate auth/permission path.
Restart OpenCode after configuration changes.

## Tool interface

The native `notion` tool takes `{tool, arguments}`:

| `tool` | `arguments` | Result |
| --- | --- | --- |
| `list` | `{}` | Live MCP tool descriptions and full input/output schemas |
| `resources` | `{}` | Available MCP documentation resources |
| `resource` | `{"uri":"notion://docs/skills"}` | Read Notion MCP documentation |
| Exact MCP name | Exact argument object from live schema | Complete MCP response |

For example: `{"tool":"notion-get-self","arguments":{}}`.
All discovery is lazy: OpenCode startup needs neither authorization nor a live
Notion connection. Browser auth is explicit, never launched by a tool call.
OAuth credentials live in MCPorter's external vault, not in this repository.

The response preserves MCP `isError`, warnings, and async task IDs. Don't report
an async acknowledgement as success: await its task, then re-fetch the target.
No automatic retries are made. A timeout/interruption can have an unknown write
outcome; inspect before retrying. MCPorter has bounded call deadlines but does
not expose per-call cancellation to this plugin.

## Skills

Seven skills are included:

- `notion-workspace`: safe workspace operations, live schema/resource discovery,
  task routing and finding/extracting missing workspace Skills.
- `notion-markdown-export`: recursive read-only Markdown snapshots with hierarchy,
  local links, private resume caches and completeness reports.
- `notion-organize`: resolve destinations, create hubs when requested, move page
  trees through the native write gate, and verify/recover multi-step operations.
- `notion-knowledge-capture`
- `notion-meeting-intelligence`
- `notion-research-documentation`
- `notion-spec-to-implementation`

The last four are unchanged official upstream skills, including their reference
files, examples and evaluations. See [provenance](skills/UPSTREAM.md).
Their `Notion:notion-*` notation maps to the native tool's exact MCP method name;
old example payloads must be checked against live schemas.

### Export a page tree

```sh
bun run export:markdown -- 'NOTION_PAGE_URL_OR_ID' "$HOME/Downloads/my-notion-export"
```

The output directory must be new. The read-only exporter follows child-page
blocks, not mentions or ordinary links. It preserves fenced code, converts common
Notion formatting and tables, rewrites exported page links, and produces a
`README.md` and `export-manifest.json`. Blank pages get placeholders; duplicate
titles get unique ID-suffixed filenames. Attachment files and comments are not
downloaded; transcripts require `--include-transcript`.

The command prints its private `.local/notion-exports/<run-id>` cache path.
Resume interrupted fetching with the **same** root and cache, using a new output:

```sh
bun run export:markdown -- 'SAME_ROOT' "$HOME/Downloads/resumed-export" \
  --cache '.local/notion-exports/RUN_ID' --resume
```

Resume reuses cached pages; start a new run for fresh data. Fetches are not a
transactional snapshot. Exit 0 means no detected omissions or broken local links;
exit 2 means a partial export was written (see the manifest). Other failures exit
nonzero. Truncated/unknown blocks, failed fetches, page limits, and database/folder
children are reported rather than silently counted as complete. Database rows and
folder contents are not recursively exported by this command.

### Organize page trees

Ask the agent to file a page under a named hub. `notion-organize` distinguishes
root pages from teamspaces/workspaces and local folders, checks exact titles and
sidebar listings, and creates a missing destination only when requested. Moving
the parent preserves its descendants; verification compares fresh ancestry,
destination children, source body and child IDs.

Writes stay on the native `notion` tool's `notion.write` path—there is intentionally
no standalone mutation command. The skill records returned destination/task IDs
privately at each completed step, so recovery doesn't create duplicate hubs.

### Extract a workspace Skill via MCP

After authentication, inspect `notion-get-enabled-skills` and `notion-download-skill`
in the live catalog. Fetch the chosen page first. With its real page ID:

```sh
mkdir -p .local
bun run mcp -- call notion.notion-download-skill \
  --args '{"id":"REAL_SKILL_PAGE_ID"}' --output raw --no-oauth \
  > .local/skill-response.json
bun run skills:extract -- .local/skill-response.json .local/review/my-skill
```

The extractor accepts the direct payload or MCP text/structured-content envelope,
handles markdown-only and archive responses, rejects unsafe paths, links, special
files, duplicate paths and oversized archives, and refuses existing destinations.
It strips a single wrapping directory while preserving supporting files. Files
are staged privately and non-executable; nothing is installed or run.
Review all files before approving installation under `skills/<name>/`.

Skill download tools may be absent on workspace-owned connections. The separate
[Agent Skills REST API](https://developers.notion.com/guides/agent-skills/overview)
supports whole-library/plugin sync but requires its **own** Read-content
connection/PAT, access to the skills databases, and `Notion-Version: 2026-03-11`.
It is not needed for normal MCP workspace management. Do not reuse or extract
MCP OAuth credentials for it.

## Development and validation

```sh
bun run check
bun test
python3 -m unittest discover -s tests -p 'test_*.py' -v
bunx skills add . --list
```

Tests cover permission ordering/rejection, conservative handling of new tools,
read-only calls, resource validation, error-envelope preservation, and safe
skill extraction, and export traversal/conversion/resume/completeness. They do not access your workspace. Live read/write behavior
and UI permission prompts require an authenticated OpenCode session.

## Sources

- [Notion MCP setup](https://developers.notion.com/guides/mcp/get-started-with-mcp)
- [Notion tools](https://developers.notion.com/guides/mcp/mcp-supported-tools)
- [Notion Skills over MCP](https://developers.notion.com/guides/mcp/notion-skills)
- [Agent Skills API](https://developers.notion.com/guides/agent-skills/overview)
- [OpenCode V2 plugins](https://opencode.ai/v2/docs/build/plugins)
- [MCPorter configuration](https://github.com/openclaw/mcporter/blob/main/docs/config.md)
