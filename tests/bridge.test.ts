import { expect, test } from "bun:test"
import { createBridge, needsWritePermission } from "../plugin/bridge.ts"

function fixture() {
  const events: string[] = []
  const bridge = createBridge(async () => ({
    async listTools(_server, options) {
      expect(options?.disableOAuth).toBe(true)
      return ["notion-get-self", "notion-update-page", "notion-new-method"].map((name) => ({ name }))
    },
    async callTool(_server, name, options) {
      expect(options?.disableOAuth).toBe(true)
      events.push(name)
      return { isError: true, content: [{ type: "text", text: "example failure" }] }
    },
    async listResources() { return { resources: [] } },
    async readResource(_server, uri) { return { contents: [{ uri, text: "docs" }] } },
    async close() { events.push("closed") },
  }))
  return { bridge, events }
}

test("reads need no write approval and preserve the MCP error envelope", async () => {
  const { bridge, events } = fixture()
  const result = await bridge.execute("notion-get-self", {}, async () => { throw Error("unexpected") })
  expect(result).toHaveProperty("isError", true)
  expect(events).toEqual(["notion-get-self"])
  await bridge.close()
  expect(events.at(-1)).toBe("closed")
})

test("writes and newly advertised methods require approval before dispatch", async () => {
  const { bridge, events } = fixture()
  for (const name of ["notion-update-page", "notion-new-method"]) {
    await expect(bridge.execute(name, {}, async () => { throw Error("denied") })).rejects.toThrow("denied")
    expect(events).toEqual([])
    await bridge.execute(name, {}, async () => { events.push("approved") })
    expect(events.splice(0)).toEqual(["approved", name])
  }
  expect(needsWritePermission("notion-get-unknown")).toBe(true)
})

test("unknown methods cannot dispatch and resource reads are restricted to Notion docs", async () => {
  const { bridge, events } = fixture()
  await expect(bridge.execute("invented", {}, async () => {})).rejects.toThrow("Unknown")
  await expect(bridge.execute("resource", { uri: "file:///etc/passwd" }, async () => {})).rejects.toThrow("notion://docs")
  expect(await bridge.execute("resource", { uri: "notion://docs/skills" }, async () => {})).toHaveProperty("contents")
  expect(events).toEqual([])
})
