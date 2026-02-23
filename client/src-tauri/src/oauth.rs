use serde::{Deserialize, Serialize};
use std::fs;
#[cfg(desktop)]
use std::sync::atomic::{AtomicBool, Ordering};
#[cfg(desktop)]
use std::sync::Arc;
#[cfg(desktop)]
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
#[cfg(desktop)]
use url::Url;

const TOKEN_FILE: &str = "client_oauth.json";
#[cfg(desktop)]
const REDIRECT_HOST: &str = "localhost";
#[cfg(desktop)]
const REDIRECT_PATH: &str = "/oauth-callback";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OAuthTokens {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: u64,
    pub scopes: Vec<String>,
}

#[cfg(desktop)]
#[derive(Debug, Clone, Serialize)]
struct OAuthCallbackPayload {
    code: String,
    state: String,
}

fn token_file_path() -> Result<std::path::PathBuf, String> {
    let home = dirs::home_dir().ok_or("Could not determine home directory")?;
    Ok(home.join(".pocketpaw").join(TOKEN_FILE))
}

#[tauri::command]
pub fn read_oauth_tokens() -> Result<OAuthTokens, String> {
    let path = token_file_path()?;
    let data = fs::read_to_string(&path).map_err(|e| format!("Failed to read tokens: {}", e))?;
    serde_json::from_str(&data).map_err(|e| format!("Failed to parse tokens: {}", e))
}

#[tauri::command]
pub fn save_oauth_tokens(tokens: OAuthTokens) -> Result<(), String> {
    let path = token_file_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Failed to create dir: {}", e))?;
    }
    let data =
        serde_json::to_string_pretty(&tokens).map_err(|e| format!("Failed to serialize: {}", e))?;
    fs::write(&path, data).map_err(|e| format!("Failed to write tokens: {}", e))
}

#[tauri::command]
pub fn clear_oauth_tokens() -> Result<(), String> {
    let path = token_file_path()?;
    if path.exists() {
        fs::remove_file(&path).map_err(|e| format!("Failed to delete tokens: {}", e))?;
    }
    Ok(())
}

#[cfg(desktop)]
#[tauri::command]
pub fn open_oauth_window(app: AppHandle, authorize_url: String) -> Result<(), String> {
    // If the window already exists, focus it
    if let Some(win) = app.get_webview_window("oauth") {
        win.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    // Validate the URL before proceeding
    let _ = Url::parse(&authorize_url).map_err(|e| format!("Invalid URL: {}", e))?;

    let callback_handled = Arc::new(AtomicBool::new(false));
    let callback_handled_nav = callback_handled.clone();
    let callback_handled_close = callback_handled.clone();

    let app_handle = app.clone();
    let app_for_close = app.clone();

    // Load a local loading page first, then navigate to the OAuth URL via JS.
    // Using WebviewUrl::External directly can result in a white screen on Windows
    // because WebView2 may not be fully initialized before the navigation starts.
    let win = WebviewWindowBuilder::new(
        &app,
        "oauth",
        WebviewUrl::App("/oauth-loading.html".into()),
    )
    .title("Sign in to PocketPaw")
    .inner_size(500.0, 700.0)
    .center()
    .resizable(true)
    .on_navigation(move |url| {
        let url_str = url.as_str();

        // Already handled — block further navigations to prevent loops
        if callback_handled_nav.load(Ordering::SeqCst) {
            return false;
        }

        // Check if this is our redirect URL
        if let Ok(nav_url) = Url::parse(url_str) {
            if nav_url.host_str() == Some(REDIRECT_HOST)
                && nav_url.path() == REDIRECT_PATH
            {
                let mut code = None;
                let mut state = None;
                for (key, value) in nav_url.query_pairs() {
                    match key.as_ref() {
                        "code" => code = Some(value.to_string()),
                        "state" => state = Some(value.to_string()),
                        _ => {}
                    }
                }

                if let (Some(code), Some(state)) = (code, state) {
                    callback_handled_nav.store(true, Ordering::SeqCst);
                    let _ = app_handle
                        .emit("oauth-callback", OAuthCallbackPayload { code, state });

                    if let Some(win) = app_handle.get_webview_window("oauth") {
                        let _ = win.close();
                    }
                }

                // Allow the navigation through — the SvelteKit callback page
                // acts as a fallback if the emit/close doesn't complete in time
                return true;
            }
        }

        true
    })
    .build()
    .map_err(|e| e.to_string())?;

    // Navigate to the OAuth URL after the local loading page is ready.
    // WebView2 queues eval() to run after the current page finishes loading,
    // so the user sees "Loading sign-in..." first, then gets redirected.
    let js_safe_url = authorize_url
        .replace('\\', "\\\\")
        .replace('\'', "\\'");
    let _ = win.eval(&format!("window.location.href='{}';", js_safe_url));

    // Only emit cancelled if the callback wasn't already handled
    win.on_window_event(move |event| {
        if let tauri::WindowEvent::Destroyed = event {
            if !callback_handled_close.load(Ordering::SeqCst) {
                let _ = app_for_close.emit("oauth-cancelled", ());
            }
        }
    });

    Ok(())
}
