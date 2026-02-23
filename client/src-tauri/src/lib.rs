mod commands;
mod context;
mod oauth;

#[cfg(desktop)]
mod quick_ask;
#[cfg(desktop)]
mod side_panel;
#[cfg(desktop)]
mod tray;
#[cfg(desktop)]
mod vibrancy;

use tauri::{Emitter, Manager};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Force X11 backend on Linux/Wayland so window positioning works.
    // Wayland does not allow apps to set their own window position.
    #[cfg(target_os = "linux")]
    {
        if std::env::var("WAYLAND_DISPLAY").is_ok() {
            std::env::set_var("GDK_BACKEND", "x11");
        }
    }
    #[allow(unused_mut)]
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_notification::init());

    // Desktop-only plugins
    #[cfg(desktop)]
    {
        builder = builder
            .plugin(tauri_plugin_global_shortcut::Builder::new().build())
            .plugin(tauri_plugin_positioner::init())
            .plugin(tauri_plugin_autostart::init(
                tauri_plugin_autostart::MacosLauncher::LaunchAgent,
                Some(vec!["--minimized"]),
            ));
    }

    #[cfg(desktop)]
    {
        builder = builder
            .manage(quick_ask::PendingQuickAsk(std::sync::Mutex::new(None)))
            .manage(side_panel::SidePanelState::default())
            .manage(vibrancy::ActiveEffect(std::sync::Mutex::new(
                vibrancy::NativeEffect::None,
            )));
    }

    builder
        .invoke_handler(tauri::generate_handler![
            commands::read_access_token,
            commands::get_pocketpaw_config_dir,
            commands::check_backend_running,
            context::get_active_context,
            oauth::read_oauth_tokens,
            oauth::save_oauth_tokens,
            oauth::clear_oauth_tokens,
            #[cfg(desktop)]
            oauth::open_oauth_window,
            #[cfg(desktop)]
            side_panel::toggle_side_panel,
            #[cfg(desktop)]
            side_panel::show_side_panel,
            #[cfg(desktop)]
            side_panel::hide_side_panel,
            #[cfg(desktop)]
            side_panel::collapse_side_panel,
            #[cfg(desktop)]
            side_panel::expand_side_panel,
            #[cfg(desktop)]
            side_panel::is_side_panel_collapsed,
            #[cfg(desktop)]
            side_panel::dock_side_panel,
            #[cfg(desktop)]
            quick_ask::toggle_quick_ask,
            #[cfg(desktop)]
            quick_ask::show_quick_ask,
            #[cfg(desktop)]
            quick_ask::hide_quick_ask,
            #[cfg(desktop)]
            quick_ask::quickask_to_sidepanel,
            #[cfg(desktop)]
            quick_ask::get_pending_quickask,
            #[cfg(desktop)]
            vibrancy::get_native_effect,
            #[cfg(desktop)]
            vibrancy::set_vibrancy_theme,
        ])
        .setup(|_app| {
            // Desktop-only: system tray + close-to-tray
            #[cfg(desktop)]
            {
                tray::setup_tray(_app.handle())?;

                let window = _app.get_webview_window("main").unwrap();

                // Apply native vibrancy/mica/acrylic effect
                let effect = vibrancy::apply_native_effect(&window, None);
                *_app
                    .state::<vibrancy::ActiveEffect>()
                    .0
                    .lock()
                    .unwrap() = effect;
                let _ = window.emit("native-effect", effect);

                let window_clone = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = window_clone.hide();
                    }
                });
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
