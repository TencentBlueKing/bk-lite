use tauri::command;

#[derive(serde::Serialize)]
pub struct PermissionStatus {
    granted: bool,
}

#[command]
pub async fn check_microphone_permission() -> Result<PermissionStatus, String> {
    #[cfg(target_os = "android")]
    {
        // 在 Android 上，我们通过 Kotlin 代码来检查权限
        // 这里返回一个默认值，实际权限检查在 MainActivity 中处理
        Ok(PermissionStatus { granted: true })
    }

    #[cfg(not(target_os = "android"))]
    {
        // 在非 Android 平台上（如桌面），假定有权限
        Ok(PermissionStatus { granted: true })
    }
}

#[command]
pub async fn request_microphone_permission() -> Result<PermissionStatus, String> {
    #[cfg(target_os = "android")]
    {
        // 在 Android 上，权限请求由 MainActivity 的 WebChromeClient 处理
        // 这个命令主要用于触发权限对话框的显示
        Ok(PermissionStatus { granted: true })
    }

    #[cfg(not(target_os = "android"))]
    {
        // 在非 Android 平台上，返回已授权
        Ok(PermissionStatus { granted: true })
    }
}
