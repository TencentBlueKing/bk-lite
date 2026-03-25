import { NextRequest, NextResponse } from 'next/server';

type VendorType = 'openai' | 'azure' | 'aliyun' | 'zhipu' | 'baidu' | 'anthropic' | 'deepseek' | 'other';

const appendPath = (apiBase: string, path: string) => {
  const normalizedBase = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
};

const buildRequest = (vendorType: VendorType, apiBase: string, apiKey: string) => {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };

  let url = apiBase;

  switch (vendorType) {
    case 'azure': {
      headers['api-key'] = apiKey;
      url = apiBase;
      break;
    }
    case 'anthropic': {
      headers['x-api-key'] = apiKey;
      headers['anthropic-version'] = '2023-06-01';
      url = apiBase.includes('/v1/models') ? apiBase : appendPath(apiBase, '/v1/models');
      break;
    }
    default: {
      headers.Authorization = `Bearer ${apiKey}`;
      url = apiBase.includes('/models') ? apiBase : appendPath(apiBase, '/models');
      break;
    }
  }

  return { url, headers };
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const vendorType = body.vendor_type as VendorType;
    const apiBase = body.api_base as string;
    const apiKey = body.api_key as string;

    if (!vendorType || !apiBase || !apiKey) {
      return NextResponse.json({ success: false, code: 'VALIDATION_ERROR', message: 'Missing required fields' }, { status: 400 });
    }

    const { url, headers } = buildRequest(vendorType, apiBase, apiKey);
    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(10000),
      cache: 'no-store',
    });

    if (response.ok) {
      return NextResponse.json({ success: true, status: response.status });
    }

    return NextResponse.json(
      {
        success: false,
        status: response.status,
        code: `${response.status}_${response.statusText.replace(/\s+/g, '_').toUpperCase()}`,
      },
      { status: 200 }
    );
  } catch (error: any) {
    const code = error?.name === 'TimeoutError' ? 'TIMEOUT' : 'NETWORK_ERROR';
    return NextResponse.json({ success: false, code, message: error?.message || 'Request failed' }, { status: 200 });
  }
}
