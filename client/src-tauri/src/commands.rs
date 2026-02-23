use std::fs;
use std::net::TcpStream;
use std::time::Duration;

/// Read the access token from ~/.pocketpaw/access_token
#[tauri::command]
pub fn read_access_token() -> Result<String, String> {
    let home = dirs::home_dir().ok_or("Could not determine home directory")?;
    let token_path = home.join(".pocketpaw").join("access_token");

    fs::read_to_string(&token_path)
        .map(|s| s.trim().to_string())
        .map_err(|e| format!("Failed to read token: {}", e))
}

/// Return the PocketPaw config directory path
#[tauri::command]
pub fn get_pocketpaw_config_dir() -> Result<String, String> {
    let home = dirs::home_dir().ok_or("Could not determine home directory")?;
    let config_dir = home.join(".pocketpaw");
    Ok(config_dir.to_string_lossy().to_string())
}

/// Check if a backend is running on the given port
#[tauri::command]
pub fn check_backend_running(port: u16) -> Result<bool, String> {
    let addr = format!("127.0.0.1:{}", port);
    match TcpStream::connect_timeout(
        &addr.parse().map_err(|e| format!("Invalid address: {}", e))?,
        Duration::from_secs(2),
    ) {
        Ok(_) => Ok(true),
        Err(_) => Ok(false),
    }
}
