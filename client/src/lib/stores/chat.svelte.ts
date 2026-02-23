import type { ChatMessage, MediaAttachment, WSEvent, PocketPawWebSocket } from "$lib/api";
import { toast } from "svelte-sonner";
import { connectionStore } from "./connection.svelte";
import { sessionStore } from "./sessions.svelte";

class ChatStore {
  messages = $state<ChatMessage[]>([]);
  isStreaming = $state(false);
  streamingContent = $state("");
  error = $state<string | null>(null);

  isEmpty = $derived(this.messages.length === 0);
  lastMessage = $derived(this.messages.at(-1) ?? null);

  private unsubs: (() => void)[] = [];
  private abortController: AbortController | null = null;

  sendMessage(content: string, media?: MediaAttachment[]): void {
    // Push user message to the list
    const userMsg: ChatMessage = {
      role: "user",
      content,
      timestamp: new Date().toISOString(),
      media,
    };
    this.messages.push(userMsg);

    // Clear any previous error
    this.error = null;

    // Send via REST SSE stream
    this.streamChat(content, media);
  }

  regenerateLastResponse(): void {
    if (this.isStreaming) return;

    // Find the last user message
    let lastUserIdx = -1;
    for (let i = this.messages.length - 1; i >= 0; i--) {
      if (this.messages[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;

    const userContent = this.messages[lastUserIdx].content;
    const userMedia = this.messages[lastUserIdx].media;

    // Remove everything after (and including) the assistant response that followed
    this.messages = this.messages.slice(0, lastUserIdx + 1);
    this.error = null;

    // Re-send via REST SSE
    this.streamChat(userContent, userMedia);
  }

  stopGeneration(): void {
    // Abort the in-flight fetch
    this.abortController?.abort();
    this.abortController = null;

    // Tell backend to stop generating
    const sessionId = sessionStore.activeSessionId;
    if (sessionId) {
      try {
        const client = connectionStore.getClient();
        client.stopChat(sessionId).catch(() => {
          // ignore — best-effort stop
        });
      } catch {
        // ignore if not connected
      }
    }

    this.finalizeStream();
  }

  loadHistory(messages: ChatMessage[]): void {
    this.messages = messages;
    this.isStreaming = false;
    this.streamingContent = "";
    this.error = null;
  }

  clearMessages(): void {
    this.messages = [];
    this.isStreaming = false;
    this.streamingContent = "";
    this.error = null;
  }

  bindEvents(ws: PocketPawWebSocket): void {
    this.disposeEvents();

    // Keep WS error listener for general connection errors
    this.unsubs.push(
      ws.on("error", (event: WSEvent) => {
        if (event.type !== "error") return;
        this.error = event.content;
        toast.error(event.content || "An error occurred");
        if (this.isStreaming) {
          this.finalizeStream();
        }
      }),
    );

    // Keep session_history listener (used when switching sessions via WS)
    this.unsubs.push(
      ws.on("session_history", (event: WSEvent) => {
        if (event.type !== "session_history") return;
        this.loadHistory(event.messages);
      }),
    );
  }

  disposeEvents(): void {
    for (const unsub of this.unsubs) unsub();
    this.unsubs = [];
  }

  private async streamChat(content: string, media?: MediaAttachment[]): Promise<void> {
    this.isStreaming = true;
    this.streamingContent = "";

    this.abortController?.abort();
    this.abortController = new AbortController();

    try {
      const client = connectionStore.getClient();
      const sessionId = sessionStore.activeSessionId ?? undefined;

      await client.chatStream(
        content,
        {
          onChunk: (data) => {
            this.streamingContent += data.content;
          },
          onStreamEnd: (data) => {
            this.finalizeStream();
            // Update active session ID if the backend returned one (e.g. new session)
            if (data.session_id && data.session_id !== sessionStore.activeSessionId) {
              sessionStore.activeSessionId = data.session_id;
            }
          },
          onError: (data) => {
            this.error = data.detail || "An error occurred";
            toast.error(this.error);
            this.finalizeStream();
          },
        },
        media,
        sessionId,
        this.abortController.signal,
      );

      // If stream ended without an explicit stream_end event, finalize
      if (this.isStreaming) {
        this.finalizeStream();
      }
    } catch (err: unknown) {
      // AbortError is expected when user stops generation
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to send message";
      this.error = message;
      toast.error(message);
      if (this.isStreaming) {
        this.finalizeStream();
      }
    } finally {
      this.abortController = null;
    }
  }

  private finalizeStream(): void {
    if (this.streamingContent) {
      this.messages.push({
        role: "assistant",
        content: this.streamingContent,
        timestamp: new Date().toISOString(),
      });
    }
    this.isStreaming = false;
    this.streamingContent = "";
  }
}

export const chatStore = new ChatStore();
