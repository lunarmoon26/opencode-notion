import { fileURLToPath } from "node:url"
import { createRuntime, type Runtime } from "mcporter"

export const configPath = fileURLToPath(new URL("./notion.mcp.json", import.meta.url))

// Unknown/new methods must go through permission approval, never inferred from a prefix.
const readOnly = new Set([
  "notion-search", "notion-ai-search", "notion-fetch", "notion-get-self",
  "notion-get-tool-access", "notion-get-users", "notion-get-teams",
  "notion-get-comments", "notion-get-async-task", "notion-query-data-sources",
  "notion-query-multiple-data-sources", "notion-query-meeting-notes",
  "notion-list-private-pages", "notion-list-shared-pages", "notion-list-favorite-pages",
  "notion-list-recent-pages", "notion-list-page-backlinks", "notion-get-enabled-skills",
  "notion-download-skill", "notion-get-file-download-urls", "notion-download-attachment",
])

export function needsWritePermission(name: string) {
  return !readOnly.has(name)
}

type Client = Pick<Runtime, "listTools" | "callTool" | "listResources" | "readResource" | "close">

export function createBridge(connect: () => Promise<Client> = () => createRuntime({ configPath })) {
  let pending: Promise<Client> | undefined
  const runtime = () => {
    pending ??= connect().catch((error) => {
      pending = undefined
      throw error
    })
    return pending
  }

  return {
    async execute(name: string, args: Record<string, unknown>, approve: () => Promise<void>) {
      const client = await runtime()
      const options = { disableOAuth: true }
      if (name === "resources") return client.listResources("notion", options)
      if (name === "resource") {
        if (typeof args.uri !== "string" || !args.uri.startsWith("notion://docs/")) {
          throw new Error("Pass a notion://docs/... URI from the resource catalog in arguments.uri.")
        }
        return client.readResource("notion", args.uri, options)
      }
      const tools = await client.listTools("notion", { ...options, includeSchema: true, timeoutMs: 30_000 })
      if (name === "list") return { tools }
      const selected = tools.find((item) => item.name === name)
      if (!selected) throw new Error(`Unknown Notion MCP tool '${name}'. Call tool: 'list' for the live catalog.`)
      if (needsWritePermission(name)) await approve()
      // Keep the full MCP envelope: callers must see isError, warnings and async task IDs.
      return client.callTool("notion", name, { ...options, args, timeoutMs: 60_000 })
    },
    async close() {
      if (pending) await (await pending).close()
    },
  }
}
