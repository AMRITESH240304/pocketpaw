import { connectionStore } from "./connection.svelte";
import { chatStore } from "./chat.svelte";
import { sessionStore } from "./sessions.svelte";
import { settingsStore } from "./settings.svelte";
import { activityStore } from "./activity.svelte";
import { skillStore } from "./skills.svelte";
import { uiStore } from "./ui.svelte";
import { platformStore } from "./platform.svelte";

export { connectionStore, chatStore, sessionStore, settingsStore, activityStore, skillStore, uiStore, platformStore };
export type { ActivityEntry } from "./activity.svelte";

// Master initialization — called once on app startup after obtaining a token.
// Sets up clients, binds events, and kicks off background data loading.
// Awaits the session-cookie login before connecting WebSocket.
export async function initializeStores(token: string, baseUrl?: string, wsToken?: string): Promise<void> {
  // Create REST client, obtain session cookie, then connect WebSocket
  await connectionStore.initialize(token, baseUrl, wsToken);
  const ws = connectionStore.getWebSocket();

  // Wire WebSocket events to stores
  chatStore.bindEvents(ws);
  sessionStore.bindEvents(ws);
  settingsStore.bindEvents(ws);
  activityStore.bindEvents(ws);

  // Load initial data via REST in background (don't block UI)
  Promise.allSettled([
    sessionStore.loadSessions(),
    settingsStore.load(),
  ]);
}
