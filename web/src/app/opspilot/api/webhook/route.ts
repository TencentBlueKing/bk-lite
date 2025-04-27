import { NextRequest, NextResponse } from 'next/server';

export const GET = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};

export const POST = async (req: NextRequest) => {
  try {
    const { sender, message, port, domain, ssl, id } = await req.json();
    const payload = { sender, message };

    let protocol = ssl ? 'https://' : 'http://';
    if (domain && (domain.startsWith('http://') || domain.startsWith('https://'))) {
      protocol = '';
    }
    const fullUrl = `${protocol}${domain || `pilot-${id}-service`}:${port}/webhooks/rest/webhook`;
    const backendResponse = await fetch(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!backendResponse.ok) {
      return NextResponse.json({ message: 'Network response was not ok' }, { status: backendResponse.status });
    }

    const json = await backendResponse.json();
    return NextResponse.json(json);
  } catch (error) {
    console.error('Fetch failed:', error);
    return NextResponse.json({ message: 'Internal Server Error' }, { status: 500 });
  }
};

export const PUT = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};

export const DELETE = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};
