import type { Session, WSEvent, PocketPawWebSocket } from "$lib/api";
import { toast } from "svelte-sonner";
import { connectionStore } from "./connection.svelte";
import { chatStore } from "./chat.svelte";

class SessionStore {
  sessions = $state<Session[]>([]);
  activeSessionId = $state<string | null>(null);
  isLoading = $state(false);

  activeSession = $derived(
    this.sessions.find((s) => s.id === this.activeSessionId) ?? null,
  );

  private unsubs: (() => void)[] = [];

  async loadSessions(limit = 50): Promise<void> {
    this.isLoading = true;
    try {
      const client = connectionStore.getClient();
      const res = await client.listSessions(limit);
      this.sessions = res.sessions;
    } catch (err) {
      console.error("[SessionStore] Failed to load sessions:", err);
      toast.error("Failed to load sessions");
    } finally {
      this.isLoading = false;
    }
  }

  async switchSession(sessionId: string): Promise<void> {
    if (sessionId === this.activeSessionId) return;

    this.activeSessionId = sessionId;

    try {
      const ws = connectionStore.getWebSocket();
      ws.switchSession(sessionId);
      // session_history event will arrive via WS and chatStore will handle it
    } catch {
      // Fallback: load history via REST
      try {
        const client = connectionStore.getClient();
        const history = await client.getSessionHistory(sessionId);
        chatStore.loadHistory(history);
      } catch (err) {
        console.error("[SessionStore] Failed to load session history:", err);
      }
    }
  }

  createNewSession(): void {
    chatStore.clearMessages();

    try {
      const ws = connectionStore.getWebSocket();
      ws.newSession();
      // new_session event will arrive with the new ID
    } catch {
      // Offline: just clear messages, no ID yet
      this.activeSessionId = null;
    }
  }

  async deleteSession(sessionId: string): Promise<void> {
    try {
      const client = connectionStore.getClient();
      await client.deleteSession(sessionId);

      this.sessions = this.sessions.filter((s) => s.id !== sessionId);

      // If we deleted the active session, switch to the most recent
      if (this.activeSessionId === sessionId) {
        const next = this.sessions[0];
        if (next) {
          await this.switchSession(next.id);
        } else {
          this.activeSessionId = null;
          chatStore.clearMessages();
        }
      }
    } catch (err) {
      console.error("[SessionStore] Failed to delete session:", err);
      toast.error("Failed to delete session");
    }
  }

  async renameSession(sessionId: string, title: string): Promise<void> {
    try {
      const client = connectionStore.getClient();
      await client.updateSessionTitle(sessionId, title);

      // Update local state
      const session = this.sessions.find((s) => s.id === sessionId);
      if (session) {
        session.title = title;
      }
    } catch (err) {
      console.error("[SessionStore] Failed to rename session:", err);
      toast.error("Failed to rename session");
    }
  }

  async searchSessions(query: string): Promise<Session[]> {
    try {
      const client = connectionStore.getClient();
      return await client.searchSessions(query);
    } catch (err) {
      console.error("[SessionStore] Failed to search sessions:", err);
      return [];
    }
  }

  async exportSession(
    sessionId: string,
    format: "json" | "md" = "json",
  ): Promise<string> {
    const client = connectionStore.getClient();
    return client.exportSession(sessionId, format);
  }

  bindEvents(ws: PocketPawWebSocket): void {
    this.disposeEvents();

    // New session created
    this.unsubs.push(
      ws.on("new_session", (event: WSEvent) => {
        if (event.type !== "new_session") return;
        this.activeSessionId = event.id;

        // Prepend a placeholder session entry
        const newSession: Session = {
          id: event.id,
          title: "New Chat",
          channel: "websocket",
          last_activity: new Date().toISOString(),
          message_count: 0,
        };
        this.sessions = [newSession, ...this.sessions];
      }),
    );

    // Connection established — set initial session ID
    this.unsubs.push(
      ws.on("connection_info", (event: WSEvent) => {
        if (event.type !== "connection_info") return;
        if (!this.activeSessionId) {
          this.activeSessionId = event.id;
        }
      }),
    );
  }

  disposeEvents(): void {
    for (const unsub of this.unsubs) unsub();
    this.unsubs = [];
  }
}

export const sessionStore = new SessionStore();
