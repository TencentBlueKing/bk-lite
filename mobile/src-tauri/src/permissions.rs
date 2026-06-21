// 麦克风权限检查已移至前端 WebView 层：
// getUserMedia → WebChromeClient.onPermissionRequest → Android 系统权限弹窗
// 详见 MainActivity.kt setupWebViewPermissions()，无需 Tauri IPC 命令。
