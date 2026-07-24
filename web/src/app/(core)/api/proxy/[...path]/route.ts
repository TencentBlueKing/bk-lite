import {NextRequest, NextResponse} from 'next/server';

import {buildProxyTargets} from './proxyTarget';

const TARGET_SERVER = process.env.NEXTAPI_URL + '/api/v1' || 'http://localhost:3000';

// SSE 连接超时时间（5 分钟），与后端 Agent 总超时一致
const SSE_TIMEOUT_MS = 300_000;
// 普通请求超时时间（60 秒）
const DEFAULT_TIMEOUT_MS = 60_000;

export async function GET(req: NextRequest) {
  return await handleProxy(req);
}

export async function POST(req: NextRequest) {
  return await handleProxy(req);
}

export async function PUT(req: NextRequest) {
  return await handleProxy(req);
}

export async function DELETE(req: NextRequest) {
  return await handleProxy(req);
}

export async function PATCH(req: NextRequest) {
  return await handleProxy(req);
}

/**
 * 检测响应是否为 SSE 流
 */
function isSSEResponse(response: Response): boolean {
  const contentType = response.headers.get('content-type') || '';
  return contentType.startsWith('text/event-stream');
}

/**
 * 处理 SSE 流式响应，确保正确透传并添加必要的响应头
 */
function handleSSEResponse(proxyResponse: Response): Response {
  const headers = new Headers(proxyResponse.headers);

  // 确保关键 SSE 响应头存在
  if (!headers.has('Cache-Control')) {
    headers.set('Cache-Control', 'no-cache, no-store, must-revalidate');
  }
  // 禁用 Nginx 缓冲，确保流式传输
  headers.set('X-Accel-Buffering', 'no');
  // 保持连接
  if (!headers.has('Connection')) {
    headers.set('Connection', 'keep-alive');
  }

  return new Response(proxyResponse.body, {
    status: proxyResponse.status,
    headers,
  });
}

// 通用代理处理函数
async function handleProxy(req: NextRequest): Promise<NextResponse | Response> {
  // 解析目标路径
  let targetPath = req.nextUrl.pathname.replace('/api/proxy', '');

  // 如果路径不以 '/' 结尾，则添加 '/'
  if (!targetPath.endsWith('/')) {
    targetPath += '/';
  }

  // 转发地址保留查询参数；日志地址仅保留 origin 与 path，避免凭据进入日志。
  const {targetUrl, logTarget} = buildProxyTargets(TARGET_SERVER, targetPath, req.nextUrl.search);

  console.log(`[PROXY] Forwarding Request: ${req.method} ${logTarget}`);

  // 复制原始请求头，追加 X-Forwarded-* 自定义请求头
  const headers = new Headers(req.headers);
  headers.set('X-Forwarded-Host', req.nextUrl.host || '');
  headers.set('X-Forwarded-For', req.headers.get('x-forwarded-for') || '');
  headers.set('X-Forwarded-Proto', req.nextUrl.protocol || 'http');

  // 创建 AbortController 用于超时控制
  const controller = new AbortController();
  // 初始使用默认超时，SSE 响应检测后会调整
  let timeoutId = setTimeout(() => controller.abort(), SSE_TIMEOUT_MS);

  // 直接转发 body，而不对其进行解析
  const fetchOptions: RequestInit & { duplex?: string } = {
    method: req.method,
    headers,
    body: req.body, // 传递 body，同时 header 保持不变
    duplex: 'half',
    signal: controller.signal,
  };

  try {
    // 转发请求并获取目标服务器响应
    const proxyResponse = await fetch(targetUrl, fetchOptions);

    // 转发响应及其内容
    console.log(`[PROXY] Response Status: ${proxyResponse.status} from ${logTarget}`);

    // 检测是否为 SSE 响应
    if (isSSEResponse(proxyResponse)) {
      console.log(`[PROXY] SSE stream detected, applying SSE handling`);
      // 清除超时，SSE 流会持续到后端关闭
      clearTimeout(timeoutId);
      return handleSSEResponse(proxyResponse);
    }

    // 非 SSE 响应，使用默认超时
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    return new NextResponse(proxyResponse.body, {
      status: proxyResponse.status,
      headers: proxyResponse.headers,
    });
  } catch (error: any) {
    clearTimeout(timeoutId);

    // 区分超时错误和其他错误
    if (error.name === 'AbortError') {
      console.error(`[PROXY ERROR] Request timeout: ${logTarget}`);
      return NextResponse.json(
        { error: 'Gateway Timeout', message: 'Request timed out' },
        { status: 504 }
      );
    }

    console.error(`[PROXY ERROR] Failed to proxy request: ${error.name || 'UnknownError'} from ${logTarget}`);
    return NextResponse.json(
      { error: 'Proxy Failed', message: error.message },
      { status: 500 }
    );
  }
}
