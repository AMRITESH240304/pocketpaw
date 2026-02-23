// Orchestrates the full OAuth 2.0 PKCE flow

import { generateCodeVerifier, generateCodeChallenge, generateState } from "./pkce";
import { saveTokens, clearTokens, type OAuthTokens } from "./token-store";
import { API_BASE } from "$lib/api/config";
const CLIENT_ID = "pocketpaw-desktop";
const REDIRECT_URI = "http://localhost:1420/oauth-callback";
const SCOPES = "admin";
const FLOW_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export interface OAuthResult {
  success: boolean;
  tokens?: OAuthTokens;
  error?: string;
}

export async function startOAuthFlow(): Promise<OAuthResult> {
  const verifier = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);
  const state = generateState();

  const authorizeUrl = new URL(`${API_BASE}/oauth/authorize`);
  authorizeUrl.searchParams.set("client_id", CLIENT_ID);
  authorizeUrl.searchParams.set("redirect_uri", REDIRECT_URI);
  authorizeUrl.searchParams.set("response_type", "code");
  authorizeUrl.searchParams.set("scope", SCOPES);
  authorizeUrl.searchParams.set("code_challenge", challenge);
  authorizeUrl.searchParams.set("code_challenge_method", "S256");
  authorizeUrl.searchParams.set("state", state);

  const { listen } = await import("@tauri-apps/api/event");
  const { invoke } = await import("@tauri-apps/api/core");

  return new Promise<OAuthResult>((resolve) => {
    let settled = false;
    let unlistenCallback: (() => void) | null = null;
    let unlistenCancelled: (() => void) | null = null;
    let unlistenError: (() => void) | null = null;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    function cleanup() {
      unlistenCallback?.();
      unlistenCancelled?.();
      unlistenError?.();
      if (timeoutId) clearTimeout(timeoutId);
    }

    function settle(result: OAuthResult) {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(result);
    }

    // Timeout fallback
    timeoutId = setTimeout(() => {
      settle({ success: false, error: "Sign-in timed out. Please try again." });
    }, FLOW_TIMEOUT_MS);

    // Listen for callback event — emitted by either:
    // 1. Rust on_navigation (fast path, if it fires for 302 redirects)
    // 2. /oauth-callback SvelteKit route (reliable fallback)
    listen<{ code: string; state: string }>("oauth-callback", async (event) => {
      const { code, state: returnedState } = event.payload;

      // Mark settled immediately to prevent oauth-cancelled from racing
      if (settled) return;
      settled = true;
      cleanup();

      if (returnedState !== state) {
        resolve({ success: false, error: "State mismatch — possible CSRF attack." });
        return;
      }

      try {
        const tokens = await exchangeCodeForTokens(code, verifier);
        await saveTokens(tokens);
        resolve({ success: true, tokens });
      } catch (err) {
        resolve({ success: false, error: `Token exchange failed: ${err}` });
      }
    }).then((unlisten) => {
      unlistenCallback = unlisten;
    });

    // Listen for error from the callback route (e.g. access_denied)
    listen<{ error: string }>("oauth-callback-error", (event) => {
      settle({ success: false, error: event.payload.error });
    }).then((unlisten) => {
      unlistenError = unlisten;
    });

    // Listen for user closing the OAuth window
    listen("oauth-cancelled", () => {
      settle({ success: false, error: "Sign-in was cancelled." });
    }).then((unlisten) => {
      unlistenCancelled = unlisten;
    });

    // Open the OAuth consent window
    invoke("open_oauth_window", { authorizeUrl: authorizeUrl.toString() }).catch((err) => {
      settle({ success: false, error: `Failed to open sign-in window: ${err}` });
    });
  });
}

async function exchangeCodeForTokens(code: string, codeVerifier: string): Promise<OAuthTokens> {
  const res = await fetch(`${API_BASE}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "authorization_code",
      code,
      code_verifier: codeVerifier,
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  const data = await res.json();

  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? null,
    expires_at: Math.floor(Date.now() / 1000) + (data.expires_in ?? 3600),
    scopes: data.scope ? data.scope.split(" ") : [],
  };
}

export async function revokeTokens(accessToken: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/oauth/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: accessToken }),
    });
  } catch {
    // Best-effort revocation
  }
  await clearTokens();
}
