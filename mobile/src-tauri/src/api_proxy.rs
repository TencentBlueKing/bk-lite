use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{command, ipc::Channel, AppHandle, Manager, State};
use tokio::sync::oneshot;

/// 每个活跃 SSE 流的取消发送端，keyed by stream_id
pub struct StreamRegistry(pub Mutex<HashMap<String, oneshot::Sender<()>>>);

#[derive(Default)]
struct Utf8ChunkDecoder {
    pending: Vec<u8>,
}

impl Utf8ChunkDecoder {
    fn push(&mut self, chunk: &[u8]) -> Result<String, String> {
        self.pending.extend_from_slice(chunk);
        match std::str::from_utf8(&self.pending) {
            Ok(text) => {
                let decoded = text.to_owned();
                self.pending.clear();
                Ok(decoded)
            }
            Err(error) if error.error_len().is_none() => {
                let valid_up_to = error.valid_up_to();
                let decoded = std::str::from_utf8(&self.pending[..valid_up_to])
                    .map_err(|decode_error| decode_error.to_string())?
                    .to_owned();
                self.pending.drain(..valid_up_to);
                Ok(decoded)
            }
            Err(error) => Err(error.to_string()),
        }
    }

    fn finish(&mut self) -> Result<String, String> {
        if self.pending.is_empty() {
            return Ok(String::new());
        }

        let decoded = std::str::from_utf8(&self.pending)
            .map_err(|error| error.to_string())?
            .to_owned();
        self.pending.clear();
        Ok(decoded)
    }
}

const COMPILED_ALLOWED_HOSTS: Option<&str> = option_env!("TAURI_ALLOWED_HOSTS");

fn configured_allowed_hosts() -> String {
    std::env::var("TAURI_ALLOWED_HOSTS")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| COMPILED_ALLOWED_HOSTS.map(str::to_owned))
        .unwrap_or_default()
}

/// 校验请求 URL 的 host 是否在指定白名单内。
///
/// 白名单格式：逗号分隔的 host[:port] 列表，例如
///   `TAURI_ALLOWED_HOSTS=bklite.example.com,api.internal.example.com:8443`
fn is_allowed_host_with_allowlist(url: &str, allowed_hosts: &str) -> bool {
    let parsed = match url::Url::parse(url) {
        Ok(u) => u,
        Err(_) => return false,
    };

    let (is_loopback, is_local_network_ip) = match parsed.host() {
        Some(url::Host::Ipv4(address)) => (
            address.is_loopback(),
            address.is_private() || address.is_link_local(),
        ),
        Some(url::Host::Ipv6(address)) => (
            address.is_loopback(),
            address.is_unique_local() || address.is_unicast_link_local(),
        ),
        Some(url::Host::Domain(domain)) => (domain.eq_ignore_ascii_case("localhost"), false),
        None => return false,
    };

    let scheme_allowed_without_explicit_allowlist =
        parsed.scheme() == "https" || (parsed.scheme() == "http" && is_loopback);
    let scheme_allowed_with_explicit_allowlist = parsed.scheme() == "https"
        || (parsed.scheme() == "http" && (is_loopback || is_local_network_ip));

    let explicit_allowlist_configured = !allowed_hosts.trim().is_empty();
    if explicit_allowlist_configured {
        if !scheme_allowed_with_explicit_allowlist {
            return false;
        }
    } else if !scheme_allowed_without_explicit_allowlist {
        return false;
    }

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

    if !explicit_allowlist_configured {
        return is_loopback;
    }

    for entry in allowed_hosts.split(',') {
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

fn is_allowed_host(url: &str) -> bool {
    let allowed_hosts = configured_allowed_hosts();
    if allowed_hosts.is_empty() {
        log::warn!("[Tauri-Proxy] 未配置 API host 白名单，当前仅放行 127.0.0.1/::1/localhost。");
    }
    is_allowed_host_with_allowlist(url, &allowed_hosts)
}

fn build_http_client(user_agent: &str) -> Result<reqwest::Client, reqwest::Error> {
    reqwest::Client::builder()
        .user_agent(user_agent)
        .connect_timeout(Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
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

#[derive(Debug, Serialize, Clone)]
#[serde(tag = "event", rename_all = "camelCase")]
pub enum StreamEvent {
    Chunk { data: String },
    End,
    Error { error: String, status: Option<u16> },
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

    log::info!(
        "🚀 [Tauri-API-{}] START: {} {}",
        request_id,
        request.method,
        request.url
    );

    // 创建 HTTP 客户端
    let client = build_http_client("Tauri-API-Proxy/1.0").map_err(|e| ApiError {
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
        _ => {
            return Err(ApiError {
                message: format!("Unsupported HTTP method: {}", request.method),
                status: None,
            })
        }
    };
    req_builder = req_builder.timeout(Duration::from_secs(60));

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
        log::info!(
            "📤 [Tauri-API-{}] Body length: {} bytes",
            request_id,
            body.len()
        );
        req_builder = req_builder.body(body.clone());
    }

    // 发送请求
    match req_builder.send().await {
        Ok(response) => {
            let status = response.status().as_u16();
            let elapsed = start_time.elapsed();

            log::info!(
                "📥 [Tauri-API-{}] Response: {} in {:?}",
                request_id,
                status,
                elapsed
            );

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
            headers.insert(
                "X-Tauri-Elapsed-Ms".to_string(),
                elapsed.as_millis().to_string(),
            );

            // 获取响应体
            match response.text().await {
                Ok(body) => {
                    log::info!(
                        "✅ [Tauri-API-{}] SUCCESS: {} bytes received",
                        request_id,
                        body.len()
                    );
                    Ok(ApiResponse {
                        status,
                        headers,
                        body,
                    })
                }
                Err(err) => {
                    log::error!(
                        "❌ [Tauri-API-{}] Failed to read response body: {}",
                        request_id,
                        err
                    );
                    Err(ApiError {
                        message: format!("Failed to read response body: {}", err),
                        status: Some(status),
                    })
                }
            }
        }
        Err(err) => {
            let elapsed = start_time.elapsed();
            log::error!(
                "❌ [Tauri-API-{}] HTTP request failed after {:?}: {}",
                request_id,
                elapsed,
                err
            );
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
    on_event: Channel<StreamEvent>,
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

    log::info!(
        "🌊 [Tauri-Stream-{}] START: {} {}",
        request_id,
        request.method,
        request.url
    );

    // 创建 HTTP 客户端
    let client = build_http_client("Tauri-Stream-Proxy/1.0").map_err(|e| ApiError {
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
        _ => {
            return Err(ApiError {
                message: format!("Unsupported HTTP method: {}", request.method),
                status: None,
            })
        }
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
    let on_event_clone = on_event.clone();

    // 在后台任务中处理流式响应
    tauri::async_runtime::spawn(async move {
        let response_result = tokio::select! {
            biased;
            _ = &mut cancel_rx => {
                log::info!("🛑 [Tauri-Stream-{}] Cancelled before response headers", request_id);
                app_clone.state::<StreamRegistry>().0.lock().unwrap_or_else(|e| e.into_inner()).remove(&stream_id_clone);
                return;
            }
            result = req_builder.send() => result,
        };

        match response_result {
            Ok(response) => {
                let status = response.status().as_u16();

                if status >= 400 {
                    let error_msg = format!("HTTP Error: {}", status);
                    log::error!("❌ [Tauri-Stream-{}] {}", request_id, error_msg);
                    let _ = on_event_clone.send(StreamEvent::Error {
                        error: error_msg,
                        status: Some(status),
                    });
                    // 清理注册表后退出
                    let reg = app_clone.state::<StreamRegistry>();
                    reg.0
                        .lock()
                        .unwrap_or_else(|e| e.into_inner())
                        .remove(&stream_id_clone);
                    return;
                }

                log::info!(
                    "📥 [Tauri-Stream-{}] Response status: {}",
                    request_id,
                    status
                );

                // 流式读取响应体
                let mut stream = response.bytes_stream();
                let mut decoder = Utf8ChunkDecoder::default();
                let mut chunk_count = 0;
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
                            match decoder.push(&chunk) {
                                Ok(text) => {
                                    if !text.is_empty() {
                                        if let Err(error) =
                                            on_event_clone.send(StreamEvent::Chunk { data: text })
                                        {
                                            log::error!(
                                                "❌ [Tauri-Stream-{}] Failed to send chunk: {}",
                                                request_id,
                                                error
                                            );
                                            cancelled = true;
                                            break;
                                        }
                                    }
                                }
                                Err(e) => {
                                    log::error!(
                                        "❌ [Tauri-Stream-{}] UTF-8 decode error: {}",
                                        request_id,
                                        e
                                    );
                                    let _ = on_event_clone.send(StreamEvent::Error {
                                        error: format!("UTF-8 decode error: {}", e),
                                        status: None,
                                    });
                                    app_clone
                                        .state::<StreamRegistry>()
                                        .0
                                        .lock()
                                        .unwrap_or_else(|e| e.into_inner())
                                        .remove(&stream_id_clone);
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            log::error!(
                                "❌ [Tauri-Stream-{}] Stream read error: {}",
                                request_id,
                                e
                            );
                            let _ = on_event_clone.send(StreamEvent::Error {
                                error: format!("Stream read error: {}", e),
                                status: None,
                            });
                            app_clone
                                .state::<StreamRegistry>()
                                .0
                                .lock()
                                .unwrap_or_else(|e| e.into_inner())
                                .remove(&stream_id_clone);
                            return;
                        }
                    }
                }

                if !cancelled {
                    match decoder.finish() {
                        Ok(text) if !text.is_empty() => {
                            if let Err(error) =
                                on_event_clone.send(StreamEvent::Chunk { data: text })
                            {
                                log::error!(
                                    "❌ [Tauri-Stream-{}] Failed to send final chunk: {}",
                                    request_id,
                                    error
                                );
                                cancelled = true;
                            }
                        }
                        Ok(_) => {}
                        Err(error) => {
                            log::error!(
                                "❌ [Tauri-Stream-{}] Incomplete UTF-8 response: {}",
                                request_id,
                                error
                            );
                            let _ = on_event_clone.send(StreamEvent::Error {
                                error: format!("Incomplete UTF-8 response: {}", error),
                                status: None,
                            });
                            cancelled = true;
                        }
                    }
                }

                // 从注册表中移除
                app_clone
                    .state::<StreamRegistry>()
                    .0
                    .lock()
                    .unwrap_or_else(|e| e.into_inner())
                    .remove(&stream_id_clone);

                if cancelled {
                    log::info!(
                        "🛑 [Tauri-Stream-{}] Task exiting after cancellation",
                        request_id
                    );
                } else {
                    log::info!(
                        "✅ [Tauri-Stream-{}] COMPLETED: {} chunks received",
                        request_id,
                        chunk_count
                    );
                    let _ = on_event_clone.send(StreamEvent::End);
                }
            }
            Err(err) => {
                log::error!(
                    "❌ [Tauri-Stream-{}] HTTP request failed: {}",
                    request_id,
                    err
                );
                app_clone
                    .state::<StreamRegistry>()
                    .0
                    .lock()
                    .unwrap_or_else(|e| e.into_inner())
                    .remove(&stream_id_clone);
                let _ = on_event_clone.send(StreamEvent::Error {
                    error: format!("HTTP request failed: {}", err),
                    status: None,
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
        log::info!(
            "🛑 [cancel_stream] Cancelled stream: {}",
            &stream_id[..8.min(stream_id.len())]
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        build_http_client, is_allowed_host_with_allowlist, redact_headers_for_log, StreamEvent,
        Utf8ChunkDecoder,
    };
    use std::{
        collections::HashMap,
        io::{Read, Write},
        net::TcpListener,
        thread,
    };

    #[test]
    fn test_utf8_chunk_decoder_preserves_code_points_split_across_network_chunks() {
        let bytes = "data: {\"text\":\"你好\"}\n".as_bytes();
        let split_at = bytes
            .windows("你".len())
            .position(|window| window == "你".as_bytes())
            .expect("find multibyte character")
            + 1;
        let mut decoder = Utf8ChunkDecoder::default();

        let first = decoder
            .push(&bytes[..split_at])
            .expect("decode valid prefix");
        let second = decoder
            .push(&bytes[split_at..])
            .expect("decode carried suffix");
        let final_text = decoder.finish().expect("finish decoder");

        assert_eq!(
            format!("{first}{second}{final_text}"),
            "data: {\"text\":\"你好\"}\n"
        );
    }

    #[test]
    fn test_stream_error_serializes_for_the_tauri_channel_contract() {
        let event = StreamEvent::Error {
            error: "HTTP Error: 401".to_string(),
            status: Some(401),
        };

        assert_eq!(
            serde_json::to_value(event).expect("serialize stream event"),
            serde_json::json!({
                "event": "error",
                "error": "HTTP Error: 401",
                "status": 401,
            }),
        );
    }

    // --- 未配置白名单（默认只放行 localhost/127.0.0.1）---

    #[test]
    fn test_no_env_allows_localhost() {
        assert!(is_allowed_host_with_allowlist(
            "http://127.0.0.1:8011/api",
            ""
        ));
        assert!(is_allowed_host_with_allowlist(
            "http://localhost:3001/dev",
            ""
        ));
        assert!(is_allowed_host_with_allowlist("http://[::1]:8011/api", ""));
    }

    #[test]
    fn test_no_env_blocks_external() {
        assert!(!is_allowed_host_with_allowlist(
            "http://169.254.169.254/latest/meta-data/",
            "",
        ));
        assert!(!is_allowed_host_with_allowlist(
            "https://evil.example.com/exfil",
            ""
        ));
        assert!(!is_allowed_host_with_allowlist(
            "http://internal-svc/secret",
            ""
        ));
    }

    // --- 已配置白名单 ---

    #[test]
    fn test_env_allows_listed_host() {
        let allowlist = "bklite.example.com,api.internal.corp:8443";
        assert!(is_allowed_host_with_allowlist(
            "https://bklite.example.com/api/v1/",
            allowlist,
        ));
        assert!(is_allowed_host_with_allowlist(
            "https://api.internal.corp:8443/stream",
            allowlist,
        ));
    }

    #[test]
    fn test_env_blocks_unlisted_host() {
        assert!(!is_allowed_host_with_allowlist(
            "http://169.254.169.254/",
            "bklite.example.com",
        ));
        assert!(!is_allowed_host_with_allowlist(
            "https://other-domain.example.com/",
            "bklite.example.com",
        ));
    }

    #[test]
    fn test_public_http_is_rejected_even_when_host_is_allowlisted() {
        assert!(!is_allowed_host_with_allowlist(
            "http://bklite.example.com/api/v1/",
            "bklite.example.com",
        ));
        assert!(is_allowed_host_with_allowlist(
            "https://bklite.example.com/api/v1/",
            "bklite.example.com",
        ));
        assert!(is_allowed_host_with_allowlist(
            "http://127.0.0.1:8011/api/v1/",
            "127.0.0.1:8011",
        ));
    }

    #[test]
    fn test_env_allows_explicit_local_network_http_hosts() {
        assert!(is_allowed_host_with_allowlist(
            "http://192.168.1.10:3001/api/proxy/core/api/get_domain_list",
            "192.168.1.10:3001",
        ));
        assert!(is_allowed_host_with_allowlist(
            "http://169.254.10.20:3001/api/proxy/core/api/get_domain_list",
            "169.254.10.20:3001",
        ));
        assert!(!is_allowed_host_with_allowlist(
            "http://169.254.169.254/latest/meta-data/",
            "192.168.1.10:3001",
        ));
    }

    #[test]
    fn test_env_host_port_distinction() {
        let allowlist = "api.corp.com:8443";
        assert!(is_allowed_host_with_allowlist(
            "https://api.corp.com:8443/ok",
            allowlist,
        ));
        assert!(!is_allowed_host_with_allowlist(
            "https://api.corp.com:9999/bad",
            allowlist,
        ));
        assert!(!is_allowed_host_with_allowlist(
            "https://api.corp.com/bad",
            allowlist,
        ));
    }

    #[test]
    fn test_invalid_url_rejected() {
        assert!(!is_allowed_host_with_allowlist(
            "not-a-url",
            "bklite.example.com"
        ));
        assert!(!is_allowed_host_with_allowlist("", "bklite.example.com"));
    }

    #[tokio::test]
    async fn test_http_client_does_not_follow_redirects() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind redirect test server");
        let address = listener.local_addr().expect("read redirect test address");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept redirect test request");
            let mut buffer = [0_u8; 1024];
            let _ = stream.read(&mut buffer);
            stream
                .write_all(
                    b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:1/blocked\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                )
                .expect("write redirect response");
        });

        let response = build_http_client("Tauri-Redirect-Test/1.0")
            .expect("build test client")
            .get(format!("http://{address}/start"))
            .send()
            .await
            .expect("return first response without following redirect");

        assert_eq!(response.status(), reqwest::StatusCode::FOUND);
        server.join().expect("join redirect test server");
    }

    #[test]
    fn test_redact_headers_for_log_masks_sensitive_headers_case_insensitively() {
        let mut headers = HashMap::new();
        headers.insert(
            "Authorization".to_string(),
            "Bearer secret-token".to_string(),
        );
        headers.insert("cookie".to_string(), "sessionid=secret".to_string());
        headers.insert("Set-Cookie".to_string(), "refresh=secret".to_string());
        headers.insert("X-Api-Key".to_string(), "api-key-secret".to_string());
        headers.insert("Content-Type".to_string(), "application/json".to_string());

        let redacted = redact_headers_for_log(&headers);

        assert_eq!(
            redacted.get("Authorization").map(String::as_str),
            Some("<redacted>")
        );
        assert_eq!(
            redacted.get("cookie").map(String::as_str),
            Some("<redacted>")
        );
        assert_eq!(
            redacted.get("Set-Cookie").map(String::as_str),
            Some("<redacted>")
        );
        assert_eq!(
            redacted.get("X-Api-Key").map(String::as_str),
            Some("<redacted>")
        );
        assert_eq!(
            redacted.get("Content-Type").map(String::as_str),
            Some("application/json")
        );

        assert_eq!(
            headers.get("Authorization").map(String::as_str),
            Some("Bearer secret-token")
        );
    }
}
