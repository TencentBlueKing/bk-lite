import { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

const TARGET_SERVER = process.env.NEXTAPI_URL + '/api/v1' || 'http://localhost:3000';

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

// 通用代理处理函数
async function handleProxy(req: NextRequest): Promise<NextResponse> {
  // 解析目标路径
  let targetPath = req.nextUrl.pathname.replace('/api/proxy', '');

  // 如果路径不以 '/' 结尾，则添加 '/'
  if (!targetPath.endsWith('/')) {
    targetPath += '/';
  }

  // 构造完整的目标 URL
  let targetUrl = `${TARGET_SERVER}${targetPath}`;

  // 拼接查询参数
  const searchParams = req.nextUrl.search;
  if (searchParams) {
    targetUrl += searchParams;
  }

  console.log(`[PROXY] Forwarding Request: ${req.method} ${targetUrl}`);

  // 复制原始请求头，追加 X-Forwarded-* 自定义请求头
  const headers = new Headers(req.headers);
  headers.set('X-Forwarded-Host', req.nextUrl.host || '');
  headers.set('X-Forwarded-For', req.headers.get('x-forwarded-for') || '');
  headers.set('X-Forwarded-Proto', req.nextUrl.protocol || 'http');

  // 直接转发 body，而不对其进行解析
  const fetchOptions: any = {
    method: req.method,
    headers,
    body: req.body, // 传递 body，同时 header 保持不变
    duplex: 'half', // 使用 any 强制传递
  };

  try {
    // 转发请求并获取目标服务器响应
    const proxyResponse = await fetch(targetUrl, fetchOptions);

    // 转发响应及其内容
    console.log(`[PROXY] Response Status: ${proxyResponse.status} from ${targetUrl}`);
    const clonedBody = proxyResponse.body;

    return new NextResponse(clonedBody, {
      status: proxyResponse.status,
      headers: proxyResponse.headers,
    });
  } catch (error: any) {
    console.error(`[PROXY ERROR] Failed to proxy request: ${error.message}`);
    return NextResponse.json(
      { error: 'Proxy Failed', message: error.message },
      { status: 500 }
    );
  }
}
