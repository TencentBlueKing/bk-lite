use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use tauri::{command, AppHandle, Emitter, State};
use futures_util::StreamExt;
use tokio::sync::oneshot;

/// 每个活跃 SSE 流的取消发送端，keyed by stream_id
pub struct StreamRegistry(pub Mutex<HashMap<String, oneshot::Sender<()>>>);

/// 校验请求 URL 的 host 是否在环境变量 TAURI_ALLOWED_HOSTS 所配置的白名单内。
///
/// 白名单格式：逗号分隔的 host[:port] 列表，例如
///   `TAURI_ALLOWED_HOSTS=bklite.example.com,api.internal.example.com:8443`
///
/// 若环境变量未设置，则默认只允许 127.0.0.1 和 localhost（开发模式兜底），
/// 并在 warn 日志中提示生产环境应显式配置。
fn is_allowed_host(url: &str) -> bool {
    let parsed = match url::Url::parse(url) {
        Ok(u) => u,
        Err(_) => return false,
    };

    let host = match parsed.host_str() {
        Some(h) => h.to_lowercase(),
        None => return false,
    };
    let port = parsed.port();

    // 构造 host 标识：带端口时用 host:port，否则只用 host
    let host_with_port = match port {
        Some(p) => format!("{}:{}", host, p),
        None => host.clone(),
    };

    let allowed_hosts_env = std::env::var("TAURI_ALLOWED_HOSTS").unwrap_or_default();

    if allowed_hosts_env.trim().is_empty() {
        // 未配置白名单时，仅放行本地开发地址
        log::warn!(
            "[Tauri-Proxy] TAURI_ALLOWED_HOSTS 未配置，生产环境请显式设置允许的后端域名。当前仅放行 127.0.0.1/::1/localhost。"
        );
        return host == "127.0.0.1" || host == "::1" || host == "localhost";
    }

    for entry in allowed_hosts_env.split(',') {
        let entry = entry.trim().to_lowercase();
        if entry.is_empty() {
            continue;
        }
        if entry == host || entry == host_with_port {
            return true;
        }
    }

    false
}

fn is_sensitive_header(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "authorization"
            | "proxy-authorization"
            | "cookie"
            | "set-cookie"
            | "api-authorization"
            | "x-api-key"
            | "api-key"
    )
}

fn redact_headers_for_log(headers: &HashMap<String, String>) -> HashMap<String, String> {
    headers
        .iter()
        .map(|(key, value)| {
            let value = if is_sensitive_header(key) {
                "<redacted>".to_string()
            } else {
                value.clone()
            };
            (key.clone(), value)
        })
        .collect()
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiRequest {
    pub url: String,
    pub method: String,
    pub headers: Option<HashMap<String, String>>,
    pub body: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct StreamChunk {
    pub stream_id: String,
    pub data: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct StreamEnd {
    pub stream_id: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct StreamError {
    pub stream_id: String,
    pub error: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiResponse {
    pub status: u16,
    pub headers: HashMap<String, String>,
    pub body: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiError {
    pub message: String,
    pub status: Option<u16>,
}

#[command]
pub async fn api_proxy(request: ApiRequest) -> Result<ApiResponse, ApiError> {
    // URL 白名单校验：防止注入脚本通过 IPC 发起任意域的 SSRF 请求
    if !is_allowed_host(&request.url) {
        log::warn!("[Tauri-API] 拒绝非白名单 URL: {}", request.url);
        return Err(ApiError {
            message: format!("URL host not in allowlist: {}", request.url),
            status: Some(403),
        });
    }

    let start_time = std::time::Instant::now();
    let request_id = uuid::Uuid::new_v4().to_string()[..8].to_string();

    log::info!("🚀 [Tauri-API-{}] START: {} {}", request_id, request.method, request.url);

    // 创建 HTTP 客户端
    let client = reqwest::Client::builder()
        .user_agent("Tauri-API-Proxy/1.0")
        .build()
        .map_err(|e| ApiError {
            message: format!("Failed to create HTTP client: {}", e),
            status: None,
        })?;

    // 构建请求
    let mut req_builder = match request.method.to_uppercase().as_str() {
        "GET" => client.get(&request.url),
        "POST" => client.post(&request.url),
        "PUT" => client.put(&request.url),
        "DELETE" => client.delete(&request.url),
        "PATCH" => client.patch(&request.url),
        "HEAD" => client.head(&request.url),
        "OPTIONS" => client.request(reqwest::Method::OPTIONS, &request.url),
        _ => return Err(ApiError {
            message: format!("Unsupported HTTP method: {}", request.method),
            status: None,
        }),
    };

    // 添加 Tauri 标识头
    req_builder = req_builder.header("X-Tauri-Proxy", "true");
    req_builder = req_builder.header("X-Tauri-Request-ID", &request_id);

    // 添加请求头
    if let Some(headers) = &request.headers {
        log::info!(
            "📨 [Tauri-API-{}] Headers: {:?}",
            request_id,
            redact_headers_for_log(headers)
        );
        for (key, value) in headers {
            req_builder = req_builder.header(key, value);
        }
    }

    // 添加请求体
    if let Some(body) = &request.body {
        log::info!("📤 [Tauri-API-{}] Body length: {} bytes", request_id, body.len());
        req_builder = req_builder.body(body.clone());
    }

    // 发送请求
    match req_builder.send().await {
        Ok(response) => {
            let status = response.status().as_u16();
            let elapsed = start_time.elapsed();
            
            log::info!("📥 [Tauri-API-{}] Response: {} in {:?}", request_id, status, elapsed);
            
            // 获取响应头
            let mut headers = HashMap::new();
            for (key, value) in response.headers() {
                if let Ok(value_str) = value.to_str() {
                    headers.insert(key.to_string(), value_str.to_string());
                }
            }

            // 添加 Tauri 代理标识头
            headers.insert("X-Tauri-Proxied".to_string(), "true".to_string());
            headers.insert("X-Tauri-Request-ID".to_string(), request_id.clone());
            headers.insert("X-Tauri-Elapsed-Ms".to_string(), elapsed.as_millis().to_string());

            // 获取响应体
            match response.text().await {
                Ok(body) => {
                    log::info!("✅ [Tauri-API-{}] SUCCESS: {} bytes received", request_id, body.len());
                    Ok(ApiResponse {
                        status,
                        headers,
                        body,
                    })
                }
                Err(err) => {
                    log::error!("❌ [Tauri-API-{}] Failed to read response body: {}", request_id, err);
                    Err(ApiError {
                        message: format!("Failed to read response body: {}", err),
                        status: Some(status),
                    })
                }
            }
        }
        Err(err) => {
            let elapsed = start_time.elapsed();
            log::error!("❌ [Tauri-API-{}] HTTP request failed after {:?}: {}", request_id, elapsed, err);
            Err(ApiError {
                message: format!("HTTP request failed: {}", err),
                status: None,
            })
        }
    }
}

#[command]
pub async fn simple_api_proxy(
    url: String,
    method: String,
    headers: Option<HashMap<String, String>>,
    body: Option<String>,
) -> Result<String, String> {
    let request = ApiRequest {
        url,
        method,
        headers,
        body,
    };

    match api_proxy(request).await {
        Ok(response) => Ok(response.body),
        Err(error) => Err(error.message),
    }
}

/// SSE 流式请求处理
/// 返回 stream_id，前端通过监听事件接收流式数据
#[command]
pub async fn api_stream_proxy(
    app: AppHandle,
    registry: State<'_, StreamRegistry>,
    request: ApiRequest,
) -> Result<String, ApiError> {
    // URL 白名单校验：与 api_proxy 保持一致
    if !is_allowed_host(&request.url) {
        log::warn!("[Tauri-Stream] 拒绝非白名单 URL: {}", request.url);
        return Err(ApiError {
            message: format!("URL host not in allowlist: {}", request.url),
            status: Some(403),
        });
    }

    let stream_id = uuid::Uuid::new_v4().to_string();
    let request_id = stream_id[..8].to_string();

    log::info!("🌊 [Tauri-Stream-{}] START: {} {}", request_id, request.method, request.url);

    // 创建 HTTP 客户端
    let client = reqwest::Client::builder()
        .user_agent("Tauri-Stream-Proxy/1.0")
        .build()
        .map_err(|e| ApiError {
            message: format!("Failed to create HTTP client: {}", e),
            status: None,
        })?;

    // 构建请求
    let mut req_builder = match request.method.to_uppercase().as_str() {
        "GET" => client.get(&request.url),
        "POST" => client.post(&request.url),
        "PUT" => client.put(&request.url),
        "DELETE" => client.delete(&request.url),
        "PATCH" => client.patch(&request.url),
        _ => return Err(ApiError {
            message: format!("Unsupported HTTP method: {}", request.method),
            status: None,
        }),
    };

    // 添加请求头
    if let Some(headers) = &request.headers {
        for (key, value) in headers {
            req_builder = req_builder.header(key, value);
        }
    }

    // 添加请求体
    if let Some(body) = &request.body {
        req_builder = req_builder.body(body.clone());
    }

    // 创建取消通道：JS 侧调用 cancel_stream 时，通过 tx 发送取消信号
    let (cancel_tx, mut cancel_rx) = oneshot::channel::<()>();
    {
        let mut map = registry.0.lock().unwrap_or_else(|e| e.into_inner());
        map.insert(stream_id.clone(), cancel_tx);
    }

    let stream_id_clone = stream_id.clone();
    let app_clone = app.clone();

    // 在后台任务中处理流式响应
    tauri::async_runtime::spawn(async move {
        match req_builder.send().await {
            Ok(response) => {
                let status = response.status().as_u16();
                
                if status >= 400 {
                    let error_msg = format!("HTTP Error: {}", status);
                    log::error!("❌ [Tauri-Stream-{}] {}", request_id, error_msg);
                    let _ = app_clone.emit("stream-error", StreamError {
                        stream_id: stream_id_clone.clone(),
                        error: error_msg,
                    });
                    // 清理注册表后退出
                    let reg = app_clone.state::<StreamRegistry>();
                    reg.0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);
                    return;
                }

                log::info!("📥 [Tauri-Stream-{}] Response status: {}", request_id, status);

                // 流式读取响应体
                let mut stream = response.bytes_stream();
                let mut buffer = String::new();
                let mut chunk_count = 0;
                let mut pending_data_prefix = false; // 标记是否有待处理的 data: 前缀
                let mut cancelled = false;

                loop {
                    let chunk_result = tokio::select! {
                        biased; // 优先检查取消信号，确保取消语义立即生效
                        // 收到取消信号，立即终止读循环
                        _ = &mut cancel_rx => {
                            log::info!("🛑 [Tauri-Stream-{}] Cancelled by client", request_id);
                            cancelled = true;
                            break;
                        }
                        item = stream.next() => {
                            match item {
                                Some(r) => r,
                                None => break, // 流自然结束
                            }
                        }
                    };
                    match chunk_result {
                        Ok(chunk) => {
                            chunk_count += 1;
                            
                            // 将字节转换为字符串
                            match String::from_utf8(chunk.to_vec()) {
                                Ok(text) => {
                                    buffer.push_str(&text);
                                    
                                    // 按行分割处理 SSE 数据
                                    let lines_vec: Vec<String> = buffer.lines().map(|s| s.to_string()).collect();
                                    
                                    // 如果最后没有换行符，保留最后一行到buffer
                                    let remaining = if !buffer.ends_with('\n') && !lines_vec.is_empty() {
                                        lines_vec.last().unwrap().clone()
                                    } else {
                                        String::new()
                                    };
                                    
                                    let lines_to_process = if !remaining.is_empty() {
                                        &lines_vec[..lines_vec.len() - 1]
                                    } else {
                                        &lines_vec[..]
                                    };
                                    
                                    buffer = remaining;
                                    
                                    // 处理完整的行，合并多行 SSE 格式
                                    let mut i = 0;
                                    while i < lines_to_process.len() {
                                        let line = &lines_to_process[i];
                                        let trimmed = line.trim();
                                        
                                        // 跳过空行和注释
                                        if trimmed.is_empty() || trimmed.starts_with(':') {
                                            i += 1;
                                            continue;
                                        }
                                        
                                        // 检测到 data: 前缀
                                        if trimmed == "data:" || trimmed.starts_with("data:") {
                                            let formatted_line = if trimmed == "data:" {
                                                // data: 单独一行，需要合并下一行的 JSON 内容
                                                if i + 1 < lines_to_process.len() {
                                                    let next_line = lines_to_process[i + 1].trim();
                                                    if next_line.starts_with('{') || next_line.starts_with('[') {
                                                        i += 1; // 跳过下一行，因为已经合并了
                                                        format!("data: {}", next_line)
                                                    } else {
                                                        format!("data: {}", next_line)
                                                    }
                                                } else {
                                                    // 没有下一行了，设置标记等待
                                                    pending_data_prefix = true;
                                                    i += 1;
                                                    continue;
                                                }
                                            } else if let Some(json_part) = trimmed.strip_prefix("data:") {
                                                // data: 和 JSON 在同一行
                                                let json_trimmed = json_part.trim();
                                                if json_trimmed.is_empty() {
                                                    // data: 后面是空的，等待下一行
                                                    pending_data_prefix = true;
                                                    i += 1;
                                                    continue;
                                                } else {
                                                    format!("data: {}", json_trimmed)
                                                }
                                            } else {
                                                line.clone()
                                            };
                                            
                                            log::debug!("📤 [Tauri-Stream-{}] Sending: {}", 
                                                request_id, 
                                                if formatted_line.len() > 100 { 
                                                    format!("{}...", &formatted_line[..100]) 
                                                } else { 
                                                    formatted_line.clone() 
                                                });
                                            
                                            // 发送数据块事件（SSE 格式，包含换行符）
                                            if let Err(e) = app_clone.emit("stream-chunk", StreamChunk {
                                                stream_id: stream_id_clone.clone(),
                                                data: format!("{}\n", formatted_line),
                                            }) {
                                                log::error!("❌ [Tauri-Stream-{}] Failed to emit chunk: {}", request_id, e);
                                                break;
                                            }
                                        } else if pending_data_prefix && (trimmed.starts_with('{') || trimmed.starts_with('[')) {
                                            // 这是 data: 后面的 JSON 内容
                                            let formatted_line = format!("data: {}", trimmed);
                                            pending_data_prefix = false;
                                            
                                            log::debug!("📤 [Tauri-Stream-{}] Sending (merged): {}", 
                                                request_id, 
                                                if formatted_line.len() > 100 { 
                                                    format!("{}...", &formatted_line[..100]) 
                                                } else { 
                                                    formatted_line.clone() 
                                                });
                                            
                                            if let Err(e) = app_clone.emit("stream-chunk", StreamChunk {
                                                stream_id: stream_id_clone.clone(),
                                                data: format!("{}\n", formatted_line),
                                            }) {
                                                log::error!("❌ [Tauri-Stream-{}] Failed to emit chunk: {}", request_id, e);
                                                break;
                                            }
                                        }
                                        
                                        i += 1;
                                    }
                                }
                                Err(e) => {
                                    log::error!("❌ [Tauri-Stream-{}] UTF-8 decode error: {}", request_id, e);
                                    let _ = app_clone.emit("stream-error", StreamError {
                                        stream_id: stream_id_clone.clone(),
                                        error: format!("UTF-8 decode error: {}", e),
                                    });
                                    app_clone.state::<StreamRegistry>().0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            log::error!("❌ [Tauri-Stream-{}] Stream read error: {}", request_id, e);
                            let _ = app_clone.emit("stream-error", StreamError {
                                stream_id: stream_id_clone.clone(),
                                error: format!("Stream read error: {}", e),
                            });
                            app_clone.state::<StreamRegistry>().0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);
                            return;
                        }
                    }
                }

                // 处理剩余的 buffer（仅在非取消情况下）
                if !cancelled && !buffer.trim().is_empty() {
                    let trimmed = buffer.trim();
                    // 确保数据行包含 data: 前缀
                    let formatted = if trimmed.starts_with("data:") {
                        buffer.clone()
                    } else if trimmed.starts_with('{') || trimmed.starts_with('[') {
                        format!("data: {}", trimmed)
                    } else {
                        buffer.clone()
                    };

                    let _ = app_clone.emit("stream-chunk", StreamChunk {
                        stream_id: stream_id_clone.clone(),
                        data: format!("{}\n", formatted),
                    });
                }

                // 从注册表中移除
                app_clone.state::<StreamRegistry>().0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);

                if cancelled {
                    log::info!("🛑 [Tauri-Stream-{}] Task exiting after cancellation", request_id);
                } else {
                    log::info!("✅ [Tauri-Stream-{}] COMPLETED: {} chunks received", request_id, chunk_count);
                    // 发送流结束事件（仅在非取消情况下）
                    let _ = app_clone.emit("stream-end", StreamEnd {
                        stream_id: stream_id_clone,
                    });
                }
            }
            Err(err) => {
                log::error!("❌ [Tauri-Stream-{}] HTTP request failed: {}", request_id, err);
                app_clone.state::<StreamRegistry>().0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);
                let _ = app_clone.emit("stream-error", StreamError {
                    stream_id: stream_id_clone,
                    error: format!("HTTP request failed: {}", err),
                });
            }
        }
    });

    Ok(stream_id)
}

/// 取消一个正在进行的 SSE 流式请求
/// JS 侧在 abortStream() 中调用此命令以通知 Rust 停止读取
#[command]
pub async fn cancel_stream(
    registry: State<'_, StreamRegistry>,
    stream_id: String,
) -> Result<(), String> {
    let mut map = registry.0.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(tx) = map.remove(&stream_id) {
        let _ = tx.send(());
        log::info!("🛑 [cancel_stream] Cancelled stream: {}", &stream_id[..8.min(stream_id.len())]);
    } else {
        log::warn!("⚠️ [cancel_stream] Stream not found (already ended?): {}", &stream_id[..8.min(stream_id.len())]);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{is_allowed_host, redact_headers_for_log};
    use std::{collections::HashMap, env};

    /// 辅助：在测试中临时设置 / 清除环境变量（串行执行，避免并发干扰）
    fn with_env<F: FnOnce()>(key: &str, val: Option<&str>, f: F) {
        let old = env::var(key).ok();
        match val {
            Some(v) => env::set_var(key, v),
            None => env::remove_var(key),
        }
        f();
        match old {
            Some(v) => env::set_var(key, v),
            None => env::remove_var(key),
        }
    }

    // --- 未配置白名单（默认只放行 localhost/127.0.0.1）---

    #[test]
    fn test_no_env_allows_localhost() {
        with_env("TAURI_ALLOWED_HOSTS", None, || {
            assert!(is_allowed_host("http://127.0.0.1:8011/api"));
            assert!(is_allowed_host("http://localhost:3001/dev"));
            assert!(is_allowed_host("http://[::1]:8011/api"));
        });
    }

    #[test]
    fn test_no_env_blocks_external() {
        with_env("TAURI_ALLOWED_HOSTS", None, || {
            // 关键测试：revert 白名单校验逻辑后此断言应失败
            assert!(!is_allowed_host("http://169.254.169.254/latest/meta-data/"));
            assert!(!is_allowed_host("https://evil.example.com/exfil"));
            assert!(!is_allowed_host("http://internal-svc/secret"));
        });
    }

    // --- 已配置白名单 ---

    #[test]
    fn test_env_allows_listed_host() {
        with_env(
            "TAURI_ALLOWED_HOSTS",
            Some("bklite.example.com,api.internal.corp:8443"),
            || {
                assert!(is_allowed_host("https://bklite.example.com/api/v1/"));
                assert!(is_allowed_host("https://api.internal.corp:8443/stream"));
            },
        );
    }

    #[test]
    fn test_env_blocks_unlisted_host() {
        with_env(
            "TAURI_ALLOWED_HOSTS",
            Some("bklite.example.com"),
            || {
                // SSRF 靶标：不在白名单内应被拒绝
                assert!(!is_allowed_host("http://169.254.169.254/"));
                assert!(!is_allowed_host("https://other-domain.example.com/"));
            },
        );
    }

    #[test]
    fn test_env_host_port_distinction() {
        // host:port 条目不应放行同 host 的其它端口
        with_env(
            "TAURI_ALLOWED_HOSTS",
            Some("api.corp.com:8443"),
            || {
                assert!(is_allowed_host("https://api.corp.com:8443/ok"));
                // 不同端口不在白名单
                assert!(!is_allowed_host("https://api.corp.com:9999/bad"));
                // 纯 host（无端口）不在白名单
                assert!(!is_allowed_host("https://api.corp.com/bad"));
            },
        );
    }

    #[test]
    fn test_invalid_url_rejected() {
        with_env("TAURI_ALLOWED_HOSTS", Some("bklite.example.com"), || {
            assert!(!is_allowed_host("not-a-url"));
            assert!(!is_allowed_host(""));
        });
    }

    #[test]
    fn test_redact_headers_for_log_masks_sensitive_headers_case_insensitively() {
        let mut headers = HashMap::new();
        headers.insert("Authorization".to_string(), "Bearer secret-token".to_string());
        headers.insert("cookie".to_string(), "sessionid=secret".to_string());
        headers.insert("Set-Cookie".to_string(), "refresh=secret".to_string());
        headers.insert("X-Api-Key".to_string(), "api-key-secret".to_string());
        headers.insert("Content-Type".to_string(), "application/json".to_string());

        let redacted = redact_headers_for_log(&headers);

        assert_eq!(redacted.get("Authorization").map(String::as_str), Some("<redacted>"));
        assert_eq!(redacted.get("cookie").map(String::as_str), Some("<redacted>"));
        assert_eq!(redacted.get("Set-Cookie").map(String::as_str), Some("<redacted>"));
        assert_eq!(redacted.get("X-Api-Key").map(String::as_str), Some("<redacted>"));
        assert_eq!(
            redacted.get("Content-Type").map(String::as_str),
            Some("application/json")
        );

        assert_eq!(headers.get("Authorization").map(String::as_str), Some("Bearer secret-token"));
    }
}
