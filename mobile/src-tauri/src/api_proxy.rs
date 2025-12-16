use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tauri::{command, AppHandle, Emitter};
use futures_util::StreamExt;

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
        log::info!("📨 [Tauri-API-{}] Headers: {:?}", request_id, headers);
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
    request: ApiRequest,
) -> Result<String, ApiError> {
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
                    return;
                }

                log::info!("📥 [Tauri-Stream-{}] Response status: {}", request_id, status);

                // 流式读取响应体
                let mut stream = response.bytes_stream();
                let mut buffer = String::new();
                let mut chunk_count = 0;
                let mut pending_data_prefix = false; // 标记是否有待处理的 data: 前缀

                while let Some(chunk_result) = stream.next().await {
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
                            return;
                        }
                    }
                }

                // 处理剩余的 buffer
                if !buffer.trim().is_empty() {
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

                log::info!("✅ [Tauri-Stream-{}] COMPLETED: {} chunks received", request_id, chunk_count);
                
                // 发送流结束事件
                let _ = app_clone.emit("stream-end", StreamEnd {
                    stream_id: stream_id_clone,
                });
            }
            Err(err) => {
                log::error!("❌ [Tauri-Stream-{}] HTTP request failed: {}", request_id, err);
                let _ = app_clone.emit("stream-error", StreamError {
                    stream_id: stream_id_clone,
                    error: format!("HTTP request failed: {}", err),
                });
            }
        }
    });

    Ok(stream_id)
}
