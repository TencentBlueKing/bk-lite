mod api_proxy;
mod permissions;

use api_proxy::{api_proxy, simple_api_proxy};
use permissions::{check_microphone_permission, request_microphone_permission};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![
      api_proxy,
      simple_api_proxy,
      check_microphone_permission,
      request_microphone_permission
    ])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
