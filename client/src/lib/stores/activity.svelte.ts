import type { WSEvent, WSSystemEvent, PocketPawWebSocket } from "$lib/api";

export interface ActivityEntry {
  id: string;
  type: "tool_start" | "tool_result" | "thinking" | "error" | "status";
  content: string;
  data?: Record<string, unknown>;
  timestamp: string;
}

let entryCounter = 0;
function nextId(): string {
  return `activity-${++entryCounter}`;
}

function formatToolStart(data: Record<string, unknown>): string {
  const tool = data.tool ?? "unknown";
  const input = data.input;
  if (input && typeof input === "object") {
    const keys = Object.keys(input as Record<string, unknown>);
    if (keys.length > 0) {
      return `${tool}(${keys.join(", ")})`;
    }
  }
  return String(tool);
}

function formatToolResult(data: Record<string, unknown>): string {
  const output = String(data.output ?? "");
  // Truncate long outputs
  return output.length > 120 ? output.slice(0, 120) + "..." : output;
}

class ActivityStore {
  entries = $state<ActivityEntry[]>([]);
  isAgentWorking = $state(false);
  currentModel = $state<string | null>(null);
  tokenUsage = $state<{ input?: number; output?: number } | null>(null);

  recentEntries = $derived(this.entries.slice(-50));
  latestEntry = $derived(this.entries.at(-1) ?? null);

  private unsubs: (() => void)[] = [];

  clear(): void {
    this.entries = [];
    this.isAgentWorking = false;
    this.tokenUsage = null;
  }

  bindEvents(ws: PocketPawWebSocket): void {
    this.disposeEvents();

    // stream_start marks beginning of agent work
    this.unsubs.push(
      ws.on("stream_start", () => {
        this.isAgentWorking = true;
        this.tokenUsage = null;
        // Don't clear entries — keep the log accumulating within a session
      }),
    );

    // system_event carries tool_start, tool_result, thinking, error
    this.unsubs.push(
      ws.on("system_event", (event: WSEvent) => {
        if (event.type !== "system_event") return;
        const sysEvent = event as WSSystemEvent;
        const now = new Date().toISOString();

        switch (sysEvent.event_type) {
          case "tool_start":
            this.entries.push({
              id: nextId(),
              type: "tool_start",
              content: formatToolStart(sysEvent.data),
              data: sysEvent.data,
              timestamp: now,
            });
            break;

          case "tool_result":
            this.entries.push({
              id: nextId(),
              type: "tool_result",
              content: formatToolResult(sysEvent.data),
              data: sysEvent.data,
              timestamp: now,
            });
            break;

          case "thinking":
            this.entries.push({
              id: nextId(),
              type: "thinking",
              content: String(sysEvent.data.content ?? ""),
              data: sysEvent.data,
              timestamp: now,
            });
            break;

          case "error":
            this.entries.push({
              id: nextId(),
              type: "error",
              content: String(sysEvent.data.detail ?? sysEvent.data.content ?? "Unknown error"),
              data: sysEvent.data,
              timestamp: now,
            });
            break;
        }
      }),
    );

    // stream_end marks agent done
    this.unsubs.push(
      ws.on("stream_end", (event: WSEvent) => {
        this.isAgentWorking = false;
        if (event.type === "stream_end" && event.usage) {
          this.tokenUsage = {
            input: event.usage.input_tokens,
            output: event.usage.output_tokens,
          };
        }
      }),
    );

    // Standalone error events (outside system_event)
    this.unsubs.push(
      ws.on("error", (event: WSEvent) => {
        if (event.type !== "error") return;
        this.entries.push({
          id: nextId(),
          type: "error",
          content: event.content,
          timestamp: new Date().toISOString(),
        });
        this.isAgentWorking = false;
      }),
    );
  }

  disposeEvents(): void {
    for (const unsub of this.unsubs) unsub();
    this.unsubs = [];
  }
}

export const activityStore = new ActivityStore();
