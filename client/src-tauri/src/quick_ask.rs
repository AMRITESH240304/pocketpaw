use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

use crate::side_panel;

/// Stores a pending message from QuickAsk for the side panel to pick up on mount.
pub struct PendingQuickAsk(pub Mutex<Option<String>>);

/// Toggle the quick ask overlay window (show/hide or create).
#[tauri::command]
pub fn toggle_quick_ask(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("quickask") {
        let visible = win.is_visible().unwrap_or(false);
        if visible {
            win.hide().map_err(|e| e.to_string())?;
        } else {
            win.show().map_err(|e| e.to_string())?;
            win.set_focus().map_err(|e| e.to_string())?;
            let _ = win.emit("quickask-shown", ());
        }
    } else {
        create_quick_ask(&app)?;
    }
    Ok(())
}

/// Show the quick ask window (create if needed).
#[tauri::command]
pub fn show_quick_ask(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("quickask") {
        win.show().map_err(|e| e.to_string())?;
        win.set_focus().map_err(|e| e.to_string())?;
        let _ = win.emit("quickask-shown", ());
    } else {
        create_quick_ask(&app)?;
    }
    Ok(())
}

/// Hide the quick ask window.
#[tauri::command]
pub fn hide_quick_ask(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("quickask") {
        win.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn create_quick_ask(app: &AppHandle) -> Result<(), String> {
    let win = WebviewWindowBuilder::new(
        app,
        "quickask",
        WebviewUrl::App("/quickask".into()),
    )
    .title("Quick Ask")
    .inner_size(600.0, 120.0)
    .always_on_top(true)
    .decorations(false)
    .transparent(true)
    .resizable(false)
    .skip_taskbar(true)
    .center()
    .build()
    .map_err(|e| e.to_string())?;

    // Apply native vibrancy effect
    crate::vibrancy::apply_native_effect(&win, None);

    Ok(())
}

/// Send a QuickAsk message to the side panel: hides QuickAsk, opens the side panel,
/// and delivers the message.
#[tauri::command]
pub fn quickask_to_sidepanel(app: AppHandle, message: String) -> Result<(), String> {
    // Hide QuickAsk
    if let Some(win) = app.get_webview_window("quickask") {
        let _ = win.hide();
    }

    // Store the message for the side panel to pick up
    let state = app.state::<PendingQuickAsk>();
    *state.0.lock().unwrap() = Some(message.clone());

    if let Some(panel) = app.get_webview_window("sidepanel") {
        // Side panel exists — show it and emit the message directly
        panel.show().map_err(|e| e.to_string())?;
        panel.set_focus().map_err(|e| e.to_string())?;
        let _ = panel.emit("quickask-message", message);
    } else {
        // Side panel doesn't exist yet — create it; it will read the pending message on mount
        side_panel::create_side_panel(&app)?;
    }

    Ok(())
}

/// Returns and clears any pending QuickAsk message (called by the side panel on mount).
#[tauri::command]
pub fn get_pending_quickask(app: AppHandle) -> Option<String> {
    let state = app.state::<PendingQuickAsk>();
    let result = state.0.lock().unwrap().take();
    result
}
