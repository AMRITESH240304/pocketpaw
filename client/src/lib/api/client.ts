import {
  ApiError,
  type BackendInfo,
  type ChannelConfig,
  type ChannelStatusMap,
  type ChannelTestResult,
  type ChatMessage,
  type HealthErrorEntry,
  type HealthSummary,
  type IdentityFiles,
  type IdentitySaveResponse,
  type MCPPreset,
  type MCPStatusMap,
  type MCPTestResponse,
  type MediaAttachment,
  type MemoryEntry,
  type MemorySettings,
  type MemoryStats,
  type Reminder,
  type RemindersResponse,
  type SSEChunk,
  type SSEError,
  type SSEStreamEnd,
  type SSEThinking,
  type SSEToolResult,
  type SSEToolStart,
  type SecurityAuditResponse,
  type Session,
  type SessionListResponse,
  type Settings,
  type Skill,
  type VersionInfo,
} from "./types";
import { BACKEND_URL, API_PREFIX } from "./config";

export class PocketPawClient {
  private baseUrl: string;
  private apiBase: string;
  private token: string | null;

  constructor(baseUrl?: string, token?: string) {
    this.baseUrl = (baseUrl ?? BACKEND_URL).replace(/\/+$/, "");
    this.apiBase = `${this.baseUrl}${API_PREFIX}`;
    this.token = token ?? null;
  }

  setToken(token: string) {
    this.token = token;
  }

  /** Returns the API base URL (e.g. "http://localhost:8888/api/v1") used for direct fetch calls */
  getApiBase(): string {
    return this.apiBase;
  }

  /** Returns the WebSocket URL derived from the base URL */
  getWsUrl(): string {
    return this.baseUrl.replace(/^http/, "ws") + `${API_PREFIX}/ws`;
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json", ...extra };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    _retried = false,
  ): Promise<T> {
    const url = `${this.apiBase}${path}`;
    const res = await fetch(url, {
      method,
      headers: this.headers(),
      body: body != null ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      // On 401, try refreshing the token and retrying once
      if (res.status === 401 && !_retried) {
        try {
          const { readTokens } = await import("$lib/auth/token-store");
          const { refreshAccessToken } = await import("$lib/auth/token-refresh");
          const tokens = await readTokens();
          if (tokens) {
            const newTokens = await refreshAccessToken(tokens);
            this.setToken(newTokens.access_token);
            return this.request<T>(method, path, body, true);
          }
        } catch {
          // Refresh failed — fall through to original error
        }
      }
      let detail: string | undefined;
      try {
        const json = await res.json();
        detail = json.detail ?? json.message ?? JSON.stringify(json);
      } catch {
        detail = await res.text().catch(() => undefined);
      }
      throw new ApiError(res.status, `${method} ${path} failed: ${res.status}`, detail);
    }
    const text = await res.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }

  private get<T>(path: string) {
    return this.request<T>("GET", path);
  }

  private post<T>(path: string, body?: unknown) {
    return this.request<T>("POST", path, body);
  }

  private put<T>(path: string, body?: unknown) {
    return this.request<T>("PUT", path, body);
  }

  private del<T>(path: string, body?: unknown) {
    return this.request<T>("DELETE", path, body);
  }

  // ---------------------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------------------

  async login(token: string): Promise<void> {
    this.token = token;
    await this.post("/auth/login", { token });
  }

  /**
   * Call the login endpoint with `credentials: "include"` so the browser
   * stores the session cookie for the backend origin.  The WebSocket handler
   * validates this cookie, avoiding the need to pass tokens in the URL.
   */
  async loginForSession(token: string): Promise<void> {
    const url = `${this.apiBase}/auth/login`;
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) {
      console.warn(`[PocketPawClient] loginForSession failed: ${res.status}`);
    }
  }

  async logout(): Promise<void> {
    await this.post("/auth/logout");
    this.token = null;
  }

  async getSessionToken(token: string): Promise<string> {
    this.token = token;
    const res = await this.post<{ session_token: string }>("/auth/session", {});
    return res.session_token;
  }

  async regenerateToken(): Promise<string> {
    const res = await this.post<{ token: string }>("/token/regenerate");
    return res.token;
  }

  // ---------------------------------------------------------------------------
  // Chat (REST)
  // ---------------------------------------------------------------------------

  async chat(content: string, media?: MediaAttachment[]): Promise<string> {
    const res = await this.post<{ response: string }>("/chat", {
      content,
      media,
    });
    return res.response;
  }

  async chatStream(
    content: string,
    handlers: {
      onChunk?: (chunk: SSEChunk) => void;
      onToolStart?: (data: SSEToolStart) => void;
      onToolResult?: (data: SSEToolResult) => void;
      onThinking?: (data: SSEThinking) => void;
      onStreamEnd?: (data: SSEStreamEnd) => void;
      onError?: (data: SSEError) => void;
    },
    media?: MediaAttachment[],
    sessionId?: string,
    signal?: AbortSignal,
  ): Promise<void> {
    const url = `${this.apiBase}/chat/stream`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ content, media, session_id: sessionId }),
      signal,
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new ApiError(res.status, `POST /chat/stream failed: ${res.status}`, detail);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new ApiError(0, "No readable stream");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const raw = line.slice(6);
          try {
            const data = JSON.parse(raw);
            switch (currentEvent) {
              case "chunk":
                handlers.onChunk?.(data);
                break;
              case "tool_start":
                handlers.onToolStart?.(data);
                break;
              case "tool_result":
                handlers.onToolResult?.(data);
                break;
              case "thinking":
                handlers.onThinking?.(data);
                break;
              case "stream_end":
                handlers.onStreamEnd?.(data);
                break;
              case "error":
                handlers.onError?.(data);
                break;
            }
          } catch {
            // skip unparseable lines
          }
          currentEvent = "";
        }
      }
    }
  }

  async stopChat(sessionId: string): Promise<void> {
    await this.post(`/chat/stop?session_id=${encodeURIComponent(sessionId)}`);
  }

  // ---------------------------------------------------------------------------
  // Sessions
  // ---------------------------------------------------------------------------

  async listSessions(limit = 50): Promise<SessionListResponse> {
    return this.get<SessionListResponse>(`/sessions?limit=${limit}`);
  }

  async getSessionHistory(sessionId: string): Promise<ChatMessage[]> {
    return this.get<ChatMessage[]>(
      `/sessions/${encodeURIComponent(sessionId)}/history`,
    );
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.del(`/sessions/${encodeURIComponent(sessionId)}`);
  }

  async updateSessionTitle(sessionId: string, title: string): Promise<void> {
    await this.post(
      `/sessions/${encodeURIComponent(sessionId)}/title`,
      { title },
    );
  }

  async searchSessions(query: string): Promise<Session[]> {
    const res = await this.get<{ sessions: Session[] }>(
      `/sessions/search?q=${encodeURIComponent(query)}`,
    );
    return res.sessions;
  }

  async exportSession(
    sessionId: string,
    format: "json" | "md" = "json",
  ): Promise<string> {
    const url = `${this.apiBase}/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`;
    const res = await fetch(url, { headers: this.headers() });
    if (!res.ok) throw new ApiError(res.status, "Export failed");
    return res.text();
  }

  // ---------------------------------------------------------------------------
  // Settings
  // ---------------------------------------------------------------------------

  async getSettings(): Promise<Settings> {
    return this.get<Settings>("/settings");
  }

  async updateSettings(settings: Partial<Settings>): Promise<void> {
    await this.put("/settings", settings);
  }

  // ---------------------------------------------------------------------------
  // Skills
  // ---------------------------------------------------------------------------

  async listSkills(): Promise<Skill[]> {
    return this.get<Skill[]>("/skills");
  }

  async searchSkills(query: string): Promise<Skill[]> {
    const res = await this.get<{ results: Skill[] }>(
      `/skills/search?q=${encodeURIComponent(query)}`,
    );
    return res.results;
  }

  async installSkill(identifier: string): Promise<void> {
    await this.post("/skills/install", { identifier });
  }

  async removeSkill(name: string): Promise<void> {
    await this.post("/skills/remove", { name });
  }

  async reloadSkills(): Promise<void> {
    await this.post("/skills/reload");
  }

  // ---------------------------------------------------------------------------
  // Memory
  // ---------------------------------------------------------------------------

  async getLongTermMemory(limit = 50): Promise<MemoryEntry[]> {
    return this.get<MemoryEntry[]>(`/memory/long_term?limit=${limit}`);
  }

  async deleteMemory(entryId: string): Promise<void> {
    await this.del(`/memory/long_term/${encodeURIComponent(entryId)}`);
  }

  async getMemorySettings(): Promise<MemorySettings> {
    return this.get<MemorySettings>("/memory/settings");
  }

  async saveMemorySettings(settings: Partial<MemorySettings>): Promise<void> {
    await this.post("/memory/settings", settings);
  }

  async getMemoryStats(): Promise<MemoryStats> {
    return this.get<MemoryStats>("/memory/stats");
  }

  // ---------------------------------------------------------------------------
  // Channels
  // ---------------------------------------------------------------------------

  async getChannelStatus(): Promise<ChannelStatusMap> {
    return this.get<ChannelStatusMap>("/channels/status");
  }

  async saveChannel(
    channel: string,
    config: Record<string, string>,
    autostart?: boolean,
  ): Promise<void> {
    const body: Record<string, unknown> = { channel, config };
    if (autostart !== undefined) body.autostart = autostart;
    await this.post("/channels/save", body);
  }

  async getChannelConfig(channel: string): Promise<ChannelConfig | null> {
    try {
      return await this.get<ChannelConfig>(
        `/channels/config?channel=${encodeURIComponent(channel)}`,
      );
    } catch {
      return null;
    }
  }

  async testChannel(channel: string): Promise<ChannelTestResult> {
    try {
      return await this.post<ChannelTestResult>("/channels/test", { channel });
    } catch {
      return { ok: false, error: "Not yet available" };
    }
  }

  async toggleChannel(
    channel: string,
    action: "start" | "stop",
  ): Promise<Record<string, unknown>> {
    return this.post("/channels/toggle", { channel, action });
  }

  async getWhatsAppQR(): Promise<{ qr: string | null; connected: boolean }> {
    return this.get("/whatsapp/qr");
  }

  async checkExtra(channel: string): Promise<{ installed: boolean; package?: string; pip_spec?: string }> {
    return this.get(`/extras/check?channel=${encodeURIComponent(channel)}`);
  }

  async installExtra(channel: string): Promise<{ status?: string; error?: string }> {
    return this.post("/extras/install", { extra: channel });
  }

  // ---------------------------------------------------------------------------
  // Backends
  // ---------------------------------------------------------------------------

  async listBackends(): Promise<BackendInfo[]> {
    return this.get<BackendInfo[]>("/backends");
  }

  async installBackend(name: string): Promise<void> {
    await this.post("/backends/install", { backend: name });
  }

  // ---------------------------------------------------------------------------
  // Health
  // ---------------------------------------------------------------------------

  async getHealth(): Promise<HealthSummary> {
    return this.get<HealthSummary>("/health");
  }

  async runHealthCheck(): Promise<HealthSummary> {
    return this.post<HealthSummary>("/health/check");
  }

  async getHealthErrors(limit = 20, search?: string): Promise<HealthErrorEntry[]> {
    let path = `/health/errors?limit=${limit}`;
    if (search) path += `&search=${encodeURIComponent(search)}`;
    return this.get<HealthErrorEntry[]>(path);
  }

  async clearHealthErrors(): Promise<void> {
    await this.del("/health/errors");
  }

  async runSecurityAudit(): Promise<SecurityAuditResponse> {
    return this.post<SecurityAuditResponse>("/security-audit");
  }

  async getVersion(): Promise<VersionInfo> {
    return this.get<VersionInfo>("/version");
  }

  // ---------------------------------------------------------------------------
  // Reminders
  // ---------------------------------------------------------------------------

  async listReminders(): Promise<Reminder[]> {
    const res = await this.get<RemindersResponse>("/reminders");
    return res.reminders;
  }

  async addReminder(text: string): Promise<void> {
    await this.post("/reminders", { text });
  }

  async deleteReminder(id: string): Promise<void> {
    await this.del(`/reminders/${encodeURIComponent(id)}`);
  }

  // ---------------------------------------------------------------------------
  // Identity
  // ---------------------------------------------------------------------------

  async getIdentity(): Promise<IdentityFiles> {
    return this.get<IdentityFiles>("/identity");
  }

  async updateIdentity(files: Partial<IdentityFiles>): Promise<IdentitySaveResponse> {
    return this.put<IdentitySaveResponse>("/identity", files);
  }

  // ---------------------------------------------------------------------------
  // Plan Mode
  // ---------------------------------------------------------------------------

  async approvePlan(): Promise<void> {
    await this.post("/plan/approve");
  }

  async rejectPlan(): Promise<void> {
    await this.post("/plan/reject");
  }

  // ---------------------------------------------------------------------------
  // Audit
  // ---------------------------------------------------------------------------

  async getAuditLog(limit = 100): Promise<unknown[]> {
    return this.get(`/audit?limit=${limit}`);
  }

  async clearAuditLog(): Promise<void> {
    await this.del("/audit");
  }

  // ---------------------------------------------------------------------------
  // MCP
  // ---------------------------------------------------------------------------

  async getMcpStatus(): Promise<MCPStatusMap> {
    return this.get<MCPStatusMap>("/mcp/status");
  }

  async addMcpServer(config: {
    name: string;
    transport: string;
    command?: string;
    args?: string[];
    url?: string;
    env?: Record<string, string>;
    enabled?: boolean;
  }): Promise<{ status: string; error?: string }> {
    return this.post("/mcp/add", config);
  }

  async removeMcpServer(name: string): Promise<void> {
    await this.post("/mcp/remove", { name });
  }

  async toggleMcpServer(name: string): Promise<{
    status: string;
    enabled?: boolean;
    connected?: boolean;
    error?: string;
  }> {
    return this.post("/mcp/toggle", { name });
  }

  async testMcpServer(config: {
    transport: string;
    command?: string;
    args?: string[];
    url?: string;
    env?: Record<string, string>;
  }): Promise<MCPTestResponse> {
    return this.post<MCPTestResponse>("/mcp/test", config);
  }

  async getMcpPresets(): Promise<MCPPreset[]> {
    return this.get<MCPPreset[]>("/mcp/presets");
  }

  async installMcpPreset(
    presetId: string,
    env?: Record<string, string>,
    extraArgs?: string[],
  ): Promise<{ status: string; connected?: boolean; error?: string }> {
    return this.post("/mcp/presets/install", {
      preset_id: presetId,
      env,
      extra_args: extraArgs,
    });
  }

  // ---------------------------------------------------------------------------
  // Remote Access
  // ---------------------------------------------------------------------------

  async getRemoteStatus(): Promise<unknown> {
    return this.get("/remote/status");
  }

  async startRemote(): Promise<void> {
    await this.post("/remote/start");
  }

  async stopRemote(): Promise<void> {
    await this.post("/remote/stop");
  }

  // ---------------------------------------------------------------------------
  // Files
  // ---------------------------------------------------------------------------

  async browseFiles(path: string): Promise<{ path: string; files: import("./types").FileEntry[] }> {
    return this.get(`/files/browse?path=${encodeURIComponent(path)}`);
  }
}
