import { Plugin } from "@opencode/plugin"
import { createBridge } from "./bridge.ts"

export default Plugin.define({
  id: "notion-mcporter",
  async setup(ctx) {
    const bridge = createBridge()
    await ctx.tool.transform((editor) => {
      editor.add({
        name: "notion",
        description:
          "Manage the connected Notion workspace through MCPorter. Use tool='list' for live tool schemas, 'resources' for MCP resources, or 'resource' with arguments.uri for Notion documentation. Otherwise pass an exact MCP tool name and its arguments. Reads run directly; writes and unknown methods require notion.write permission. Authenticate in a terminal first using the project's auth command. Never retry an ambiguous write blindly.",
        input: {
          type: "object",
          properties: {
            tool: { type: "string", description: "Exact MCP tool name, or list, resources, resource." },
            arguments: { type: "object", additionalProperties: true },
          },
          required: ["tool", "arguments"],
          additionalProperties: false,
        },
        async execute(input, context) {
          const args = input as { tool: string; arguments: Record<string, unknown> }
          context.signal.throwIfAborted()
          const value = await bridge.execute(args.tool, args.arguments, async () => {
            await ctx.permission.assert({
              sessionID: context.sessionID,
              agent: context.agent,
              source: { type: "tool", messageID: context.messageID, id: context.id },
              action: "notion.write",
              resources: [args.tool],
              save: [args.tool],
              metadata: { tool: args.tool, arguments: args.arguments },
            })
            context.signal.throwIfAborted()
          })
          return { content: JSON.stringify(value, null, 2) }
        },
      })
    })
    return () => bridge.close()
  },
})
