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

#[cfg(target_os = "ios")]
fn apply_native_page_zoom_policy(webview: &tauri::WebviewWindow) -> tauri::Result<()> {
  webview.with_webview(|platform_webview| unsafe {
    let webview = &*platform_webview
      .inner()
      .cast::<objc2::runtime::AnyObject>();
    let scroll_view: *mut objc2::runtime::AnyObject = objc2::msg_send![webview, scrollView];

    if let Some(scroll_view) = scroll_view.as_ref() {
      let _: () = objc2::msg_send![scroll_view, setMinimumZoomScale: 1.0_f64];
      let _: () = objc2::msg_send![scroll_view, setMaximumZoomScale: 1.0_f64];

      let pinch_gesture: *mut objc2::runtime::AnyObject =
        objc2::msg_send![scroll_view, pinchGestureRecognizer];
      if let Some(pinch_gesture) = pinch_gesture.as_ref() {
        let _: () = objc2::msg_send![pinch_gesture, setEnabled: false];
      }
    }
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

  #[cfg(target_os = "ios")]
  let builder = builder.on_page_load(|webview, payload| {
    use tauri::{webview::PageLoadEvent, Manager};

    if matches!(payload.event(), PageLoadEvent::Finished) {
      if let Some(main_webview) = webview
        .app_handle()
        .get_webview_window(webview.label())
      {
        let _ = apply_native_page_zoom_policy(&main_webview);
      }
    }
  });

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
          apply_native_page_zoom_policy(&main_webview)?;
        }
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
