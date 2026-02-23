import type { WSAction, WSEvent } from "./types";

export type ConnectionState = "connecting" | "connected" | "disconnected";

type EventType = WSEvent["type"] | "*";
type EventHandler = (event: WSEvent) => void;

import { BACKEND_URL, API_PREFIX } from "./config";

const DEFAULT_WS_URL = BACKEND_URL.replace(/^http/, "ws") + `${API_PREFIX}/ws`;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 30_000;

export class PocketPawWebSocket {
  private url: string;
  private token: string | null;
  private ws: WebSocket | null = null;
  private listeners = new Map<EventType, Set<EventHandler>>();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private intentionalClose = false;

  state: ConnectionState = "disconnected";
  sessionId: string | null = null;

  private stateListeners = new Set<(state: ConnectionState) => void>();

  constructor(url?: string, token?: string) {
    this.url = url ?? DEFAULT_WS_URL;
    this.token = token ?? null;
  }

  // ---------------------------------------------------------------------------
  // Connection lifecycle
  // ---------------------------------------------------------------------------

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.intentionalClose = false;
    this.setState("connecting");

    const wsUrl = this.token ? `${this.url}?token=${encodeURIComponent(this.token)}` : this.url;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.setState("connected");
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSEvent;
        this.handleEvent(data);
      } catch {
        // ignore unparseable messages
      }
    };

    this.ws.onclose = () => {
      this.cleanup();
      this.setState("disconnected");
      if (!this.intentionalClose) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror, so reconnect is handled there
    };
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.cancelReconnect();
    this.cleanup();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
  }

  send(action: WSAction): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[PocketPawWS] Cannot send — not connected");
      return;
    }
    this.ws.send(JSON.stringify(action));
  }

  // ---------------------------------------------------------------------------
  // Event listeners
  // ---------------------------------------------------------------------------

  on(type: EventType, handler: EventHandler): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(handler);
    return () => {
      this.listeners.get(type)?.delete(handler);
    };
  }

  onAny(handler: EventHandler): () => void {
    return this.on("*", handler);
  }

  onStateChange(handler: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(handler);
    return () => {
      this.stateListeners.delete(handler);
    };
  }

  // ---------------------------------------------------------------------------
  // Convenience methods
  // ---------------------------------------------------------------------------

  chat(content: string, media?: import("./types").MediaAttachment[]): void {
    this.send({ action: "chat", message: content, media });
  }

  stopGeneration(): void {
    this.send({ action: "stop" });
  }

  newSession(): void {
    this.send({ action: "new_session" });
  }

  switchSession(sessionId: string): void {
    this.send({ action: "switch_session", session_id: sessionId });
  }

  resumeSession(): void {
    this.send({ action: "resume_session" });
  }

  requestSettings(): void {
    this.send({ action: "get_settings" });
  }

  updateSettings(settings: Record<string, unknown>): void {
    this.send({ action: "settings", ...settings });
  }

  saveApiKey(provider: string, key: string): void {
    this.send({ action: "save_api_key", provider, key });
  }

  browseFiles(path: string, context?: string): void {
    this.send({ action: "file_browse", path, context });
  }

  reconnectWithToken(token: string): void {
    this.token = token;
    this.disconnect();
    this.connect();
  }

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  private handleEvent(event: WSEvent): void {
    // Track session ID from connection_info
    if (event.type === "connection_info" && "id" in event) {
      this.sessionId = event.id;
    }
    if (event.type === "new_session" && "id" in event) {
      this.sessionId = event.id;
    }

    // Dispatch to typed listeners
    const typed = this.listeners.get(event.type);
    if (typed) {
      for (const handler of typed) {
        try {
          handler(event);
        } catch (err) {
          console.error(`[PocketPawWS] Handler error for "${event.type}":`, err);
        }
      }
    }

    // Dispatch to wildcard listeners
    const wildcard = this.listeners.get("*");
    if (wildcard) {
      for (const handler of wildcard) {
        try {
          handler(event);
        } catch (err) {
          console.error("[PocketPawWS] Wildcard handler error:", err);
        }
      }
    }
  }

  private setState(state: ConnectionState): void {
    if (this.state === state) return;
    this.state = state;
    for (const handler of this.stateListeners) {
      try {
        handler(state);
      } catch (err) {
        console.error("[PocketPawWS] State listener error:", err);
      }
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        // Send a small ping message to keep the connection alive.
        // The backend ignores unknown actions gracefully.
        this.ws.send(JSON.stringify({ action: "ping" }));
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private cleanup(): void {
    this.stopHeartbeat();
  }

  private scheduleReconnect(): void {
    this.cancelReconnect();
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, this.reconnectAttempt),
      RECONNECT_MAX_MS,
    );
    this.reconnectAttempt++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private cancelReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
