mod api_proxy;
mod permissions;

use api_proxy::{api_proxy, simple_api_proxy, api_stream_proxy, cancel_stream, StreamRegistry};
use permissions::{check_microphone_permission, request_microphone_permission};
use std::collections::HashMap;
use std::sync::Mutex;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .manage(StreamRegistry(Mutex::new(HashMap::new())))
    .plugin(tauri_plugin_store::Builder::new().build())
    .invoke_handler(tauri::generate_handler![
      api_proxy,
      simple_api_proxy,
      api_stream_proxy,
      cancel_stream,
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
