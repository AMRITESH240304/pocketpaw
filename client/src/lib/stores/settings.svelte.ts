import type { Settings, WSEvent, PocketPawWebSocket } from "$lib/api";
import { connectionStore } from "./connection.svelte";

class SettingsStore {
  settings = $state<Settings | null>(null);
  isLoading = $state(false);

  agentBackend = $derived(this.settings?.agent_backend ?? "claude_agent_sdk");

  model = $derived.by(() => {
    const s = this.settings;
    if (!s) return "";
    switch (s.agent_backend) {
      case "claude_agent_sdk": return s.claude_sdk_model ?? s.anthropic_model ?? "";
      case "openai_agents": return s.openai_agents_model ?? s.openai_model ?? "";
      case "google_adk": return s.google_adk_model ?? s.gemini_model ?? "";
      case "codex_cli": return s.codex_cli_model ?? "";
      case "copilot_sdk": return s.copilot_sdk_model ?? "";
      case "opencode": return s.opencode_model ?? "";
      default: return "";
    }
  });

  private unsubs: (() => void)[] = [];

  async load(): Promise<void> {
    this.isLoading = true;
    try {
      const client = connectionStore.getClient();
      this.settings = await client.getSettings();
    } catch (err) {
      console.error("[SettingsStore] Failed to load settings:", err);
    } finally {
      this.isLoading = false;
    }
  }

  async update(patch: Partial<Settings>): Promise<void> {
    try {
      const client = connectionStore.getClient();
      await client.updateSettings(patch);
      // Merge into local state
      if (this.settings) {
        this.settings = { ...this.settings, ...patch };
      }
    } catch (err) {
      console.error("[SettingsStore] Failed to update settings:", err);
      throw err;
    }
  }

  saveApiKey(provider: string, key: string): void {
    try {
      const ws = connectionStore.getWebSocket();
      ws.saveApiKey(provider, key);
    } catch (err) {
      console.error("[SettingsStore] Failed to save API key:", err);
    }
  }

  bindEvents(ws: PocketPawWebSocket): void {
    this.disposeEvents();

    // Settings pushed from server (e.g., after save_api_key)
    this.unsubs.push(
      ws.on("settings", (event: WSEvent) => {
        if (event.type !== "settings") return;
        this.settings = event.content;
      }),
    );
  }

  disposeEvents(): void {
    for (const unsub of this.unsubs) unsub();
    this.unsubs = [];
  }
}

export const settingsStore = new SettingsStore();
