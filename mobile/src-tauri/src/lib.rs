mod api_proxy;

use api_proxy::{api_proxy, simple_api_proxy, api_stream_proxy, cancel_stream, StreamRegistry};
use std::collections::HashMap;
use std::sync::Mutex;

#[cfg(target_os = "ios")]
fn apply_back_forward_navigation_gestures(
  webview: &tauri::WebviewWindow,
  enabled: bool,
) -> tauri::Result<()> {
  webview.with_webview(move |platform_webview| unsafe {
    let webview = &*platform_webview
      .inner()
      .cast::<objc2::runtime::AnyObject>();
    let _: () = objc2::msg_send![
      webview,
      setAllowsBackForwardNavigationGestures: enabled
    ];
  })
}

#[tauri::command]
fn set_back_forward_navigation_gestures(
  app: tauri::AppHandle,
  enabled: bool,
) -> Result<(), String> {
  #[cfg(target_os = "ios")]
  {
    use tauri::Manager;

    let webview = app
      .get_webview_window("main")
      .ok_or_else(|| "main webview is not available".to_string())?;
    apply_back_forward_navigation_gestures(&webview, enabled)
      .map_err(|error| error.to_string())?;
  }

  #[cfg(not(target_os = "ios"))]
  let _ = (app, enabled);

  Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let builder = tauri::Builder::default();

  #[cfg(target_os = "ios")]
  let builder = builder.plugin(tauri_plugin_ios_webview_insets::init());

  builder
    .manage(StreamRegistry(Mutex::new(HashMap::new())))
    .plugin(tauri_plugin_store::Builder::new().build())
    .invoke_handler(tauri::generate_handler![
      api_proxy,
      simple_api_proxy,
      api_stream_proxy,
      cancel_stream,
      set_back_forward_navigation_gestures,
    ])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      #[cfg(target_os = "ios")]
      {
        use tauri::Manager;

        if let Some(main_webview) = app.get_webview_window("main") {
          apply_back_forward_navigation_gestures(&main_webview, false)?;
        }
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
