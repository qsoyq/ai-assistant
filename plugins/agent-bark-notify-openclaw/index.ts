import { spawn } from "node:child_process";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeContext(ctx: unknown): JsonRecord {
  return isRecord(ctx) ? ctx : {};
}

async function runBarkHook(event: string, payload: JsonRecord): Promise<void> {
  await new Promise<void>((resolve) => {
    const child = spawn(
      "ai-assistant",
      ["agent-bark-notify", "hook", "--runtime", "openclaw", "--event", event, "--summary-mode", "extract"],
      { stdio: ["pipe", "ignore", "ignore"] },
    );

    child.on("error", () => resolve());
    child.on("close", () => resolve());
    child.stdin.end(JSON.stringify(payload));
  });
}

export default definePluginEntry({
  id: "agent-bark-notify-openclaw",
  name: "Agent Bark Notify",
  description: "Send Bark notifications from OpenClaw lifecycle hooks through ai-assistant.",
  register(api) {
    api.on(
      "agent_end",
      async (event, ctx) => {
        const context = normalizeContext(ctx);
        await runBarkHook(event.success ? "completion" : "failed", {
          source: "openclaw",
          hook_event_name: "agent_end",
          success: event.success,
          error: event.error,
          durationMs: event.durationMs,
          runId: event.runId ?? context.runId,
          sessionId: context.sessionId,
          sessionKey: context.sessionKey,
          agentId: context.agentId,
          workspaceDir: context.workspaceDir,
          channel: context.channel,
          messageProvider: context.messageProvider,
        });
      },
      { priority: -100, timeoutMs: 5000 },
    );
  },
});
