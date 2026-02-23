// ---------------------------------------------------------------------------
// PocketPaw API Types
// Matches the Python backend's event model and REST response shapes exactly.
// ---------------------------------------------------------------------------

// -- Media ------------------------------------------------------------------

export interface MediaAttachment {
  type: "image" | "file" | "audio";
  url?: string;
  data?: string;
  filename?: string;
  mime_type?: string;
}

// -- Chat Messages ----------------------------------------------------------

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
  media?: MediaAttachment[];
}

// -- Sessions ---------------------------------------------------------------

export interface Session {
  id: string;
  title: string;
  channel: string;
  last_activity: string;
  message_count: number;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

// -- Settings ---------------------------------------------------------------

export interface Settings {
  agent_backend: string;

  // Per-backend provider/model/max_turns
  claude_sdk_provider?: string;
  claude_sdk_model?: string;
  claude_sdk_max_turns?: number;
  openai_agents_provider?: string;
  openai_agents_model?: string;
  openai_agents_max_turns?: number;
  google_adk_model?: string;
  google_adk_max_turns?: number;
  codex_cli_model?: string;
  codex_cli_max_turns?: number;
  copilot_sdk_provider?: string;
  copilot_sdk_model?: string;
  copilot_sdk_max_turns?: number;
  opencode_base_url?: string;
  opencode_model?: string;
  opencode_max_turns?: number;

  // Global LLM provider settings
  llm_provider?: string;
  ollama_host?: string;
  ollama_model?: string;
  anthropic_model?: string;
  openai_model?: string;
  openai_compatible_base_url?: string;
  openai_compatible_model?: string;
  openai_compatible_max_tokens?: number;
  gemini_model?: string;

  // Memory
  memory_backend?: string;
  mem0_auto_learn?: boolean;
  mem0_llm_provider?: string;
  mem0_llm_model?: string;
  mem0_embedder_provider?: string;
  mem0_embedder_model?: string;
  mem0_vector_store?: string;
  mem0_ollama_base_url?: string;

  // Security/features
  tool_profile?: string;
  plan_mode?: boolean;
  plan_mode_tools?: string;
  smart_routing_enabled?: boolean;
  bypass_permissions?: boolean;
  injection_scan_enabled?: boolean;
  injection_scan_llm?: boolean;
  self_audit_enabled?: boolean;
  self_audit_schedule?: string;

  // Audio
  tts_provider?: string;
  tts_voice?: string;
  stt_provider?: string;
  stt_model?: string;
  ocr_provider?: string;

  [key: string]: unknown;
}

// -- Skills -----------------------------------------------------------------

export interface Skill {
  name: string;
  description: string;
  argument_hint: string;
}

// -- Channels ---------------------------------------------------------------

export interface ChannelInfo {
  configured: boolean;
  running: boolean;
  autostart: boolean;
  mode?: string;
  error?: string;
}

export type ChannelStatusMap = Record<string, ChannelInfo>;

export interface ChannelConfig {
  channel: string;
  values: Record<string, string>;
  has_secret: Record<string, boolean>;
}

export interface ChannelTestResult {
  ok: boolean;
  error?: string;
}

// -- Backends ---------------------------------------------------------------

export interface BackendInstallHint {
  verify_import?: string;
  verify_attr?: string;
  pip_spec?: string;
}

export interface BackendInfo {
  name: string;
  displayName: string;
  available: boolean;
  capabilities: string[];
  builtinTools: string[];
  requiredKeys: string[];
  supportedProviders: string[];
  installHint: BackendInstallHint;
  beta: boolean;
}

// -- Memory -----------------------------------------------------------------

export interface MemoryEntry {
  id: string;
  content: string;
  timestamp: string;
  tags: string[];
}

export interface MemorySettings {
  memory_backend: string;
  memory_use_inference: boolean;
  mem0_llm_provider: string;
  mem0_llm_model: string;
  mem0_embedder_provider: string;
  mem0_embedder_model: string;
  mem0_vector_store: string;
  mem0_ollama_base_url: string;
  mem0_auto_learn: boolean;
}

export interface MemoryStats {
  backend: string;
  total_memories: number | string;
  memories_by_type?: {
    long_term?: number;
    daily?: number;
    session?: number;
  };
}

// -- Identity ---------------------------------------------------------------

export interface IdentityFiles {
  identity_file: string;
  soul_file: string;
  style_file: string;
  instructions_file: string;
  user_file: string;
}

export interface IdentitySaveResponse {
  ok: boolean;
  updated: string[];
}

// -- Health -----------------------------------------------------------------

export interface HealthIssue {
  check_id: string;
  name: string;
  category: "config" | "connectivity" | "storage" | "updates";
  status: "ok" | "warning" | "critical";
  message: string;
  fix_hint: string;
  timestamp: string;
  details?: string[] | null;
}

export interface HealthSummary {
  status: "unknown" | "healthy" | "degraded" | "unhealthy";
  check_count: number;
  issues: HealthIssue[];
  error?: string;
  last_check?: string;
}

export interface HealthErrorEntry {
  id: string;
  timestamp: string;
  source: string;
  severity: "error" | "warning" | "critical";
  message: string;
  traceback?: string;
  context?: Record<string, unknown>;
}

export interface SecurityCheckResult {
  check: string;
  passed: boolean;
  message: string;
  fixable: boolean;
}

export interface SecurityAuditResponse {
  total: number;
  passed: number;
  issues: number;
  results: SecurityCheckResult[];
}

// -- MCP Servers ------------------------------------------------------------

export interface MCPServerInfo {
  connected: boolean;
  connecting?: boolean;
  tool_count: number;
  error: string;
  transport: string;
  enabled: boolean;
}

export type MCPStatusMap = Record<string, MCPServerInfo>;

export interface MCPPresetEnvKey {
  key: string;
  label: string;
  required: boolean;
  placeholder: string;
  secret: boolean;
}

export interface MCPPreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  package: string;
  transport: string;
  url?: string;
  docs_url: string;
  needs_args: boolean;
  oauth: boolean;
  installed: boolean;
  env_keys: MCPPresetEnvKey[];
}

export interface MCPTestResponse {
  connected: boolean;
  error?: string;
  tools: { name: string; description: string }[];
}

// -- Version ----------------------------------------------------------------

export interface VersionInfo {
  version: string;
  python: string;
  agent_backend: string;
}

// -- Reminders --------------------------------------------------------------

export interface Reminder {
  id: string;
  text: string;
  trigger_at: string;
  created_at: string;
  time_remaining: string;
}

export interface RemindersResponse {
  reminders: Reminder[];
}

// -- Files ------------------------------------------------------------------

export interface FileEntry {
  name: string;
  isDir: boolean;
  size?: string;
}

// -- Token Usage ------------------------------------------------------------

export interface TokenUsage {
  input_tokens?: number;
  output_tokens?: number;
  [key: string]: unknown;
}

// -- WebSocket Actions (client → server) ------------------------------------

export type WSAction =
  | { action: "chat"; message: string; media?: MediaAttachment[] }
  | { action: "stop" }
  | { action: "new_session" }
  | { action: "switch_session"; session_id: string }
  | { action: "resume_session" }
  | { action: "get_settings" }
  | { action: "settings"; [key: string]: unknown }
  | { action: "save_api_key"; provider: string; key: string }
  | { action: "authenticate"; token: string }
  | { action: "tool"; tool: string; path?: string }
  | { action: "file_browse"; path: string; context?: string };

// -- WebSocket Events (server → client) -------------------------------------

export interface WSConnectionInfo {
  type: "connection_info";
  content: string;
  id: string;
}

export interface WSSessionHistory {
  type: "session_history";
  session_id: string;
  messages: ChatMessage[];
}

export interface WSNewSession {
  type: "new_session";
  id: string;
}

export interface WSMessage {
  type: "message";
  content: string;
  is_stream_chunk?: boolean;
  metadata?: Record<string, unknown>;
}

export interface WSStreamStart {
  type: "stream_start";
}

export interface WSStreamEnd {
  type: "stream_end";
  media?: string[];
  usage?: TokenUsage;
}

export interface WSSystemEvent {
  type: "system_event";
  event_type:
    | "tool_start"
    | "tool_result"
    | "thinking"
    | "thinking_done"
    | "error";
  data: Record<string, unknown>;
}

export interface WSSettings {
  type: "settings";
  content: Settings;
}

export interface WSNotification {
  type: "notification";
  content: string;
}

export interface WSError {
  type: "error";
  content: string;
}

export interface WSFiles {
  type: "files";
  path: string;
  files: FileEntry[];
  error?: string;
}

export interface WSHealthUpdate {
  type: "health_update";
  data: HealthSummary;
}

export interface WSReminders {
  type: "reminders";
  reminders: Reminder[];
}

export interface WSReminderAdded {
  type: "reminder_added";
  reminder: Reminder;
}

export interface WSReminderDeleted {
  type: "reminder_deleted";
  id: string;
}

export interface WSSkills {
  type: "skills";
  skills: Skill[];
}

export type WSEvent =
  | WSConnectionInfo
  | WSSessionHistory
  | WSNewSession
  | WSMessage
  | WSStreamStart
  | WSStreamEnd
  | WSSystemEvent
  | WSSettings
  | WSNotification
  | WSError
  | WSFiles
  | WSHealthUpdate
  | WSReminders
  | WSReminderAdded
  | WSReminderDeleted
  | WSSkills;

// -- SSE Events (from POST /chat/stream) ------------------------------------

export interface SSEChunk {
  content: string;
  type: string;
}

export interface SSEToolStart {
  tool: string;
  input: Record<string, unknown>;
}

export interface SSEToolResult {
  tool: string;
  output: string;
}

export interface SSEThinking {
  content: string;
}

export interface SSEStreamEnd {
  session_id: string;
  usage?: TokenUsage;
}

export interface SSEError {
  detail: string;
}

// -- API Error --------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
