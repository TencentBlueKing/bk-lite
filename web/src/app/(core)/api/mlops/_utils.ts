import { NextRequest, NextResponse } from 'next/server';

const getMlopsTargetServer = () => {
  if (!process.env.NEXTAPI_URL) {
    throw new Error('NEXTAPI_URL is not configured');
  }

  return `${process.env.NEXTAPI_URL}/api/v1/mlops`;
};

export const forwardMlopsRequest = async (req: NextRequest, targetPath: string): Promise<NextResponse> => {
  const targetServer = getMlopsTargetServer();
  let targetUrl = `${targetServer}${targetPath}`;

  const searchParams = req.nextUrl.search;
  if (searchParams) {
    targetUrl += searchParams;
  }

  const headers = new Headers(req.headers);

  const fetchOptions: RequestInit & { duplex?: 'half' } = {
    method: req.method,
    headers,
  };

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    fetchOptions.body = req.body;
    fetchOptions.duplex = 'half';
  }

  try {
    const proxyResponse = await fetch(targetUrl, fetchOptions);

    return new NextResponse(proxyResponse.body, {
      status: proxyResponse.status,
      headers: proxyResponse.headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';

    return NextResponse.json(
      { error: 'Proxy Failed', message },
      { status: 500 }
    );
  }
};
