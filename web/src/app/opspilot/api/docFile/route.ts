import { NextRequest, NextResponse } from 'next/server';

export const GET = async (req: NextRequest) => {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get('id');

  if (!id) {
    return NextResponse.json({ message: 'Missing required id parameter' }, { status: 400 });
  }

  try {
    const authorizationHeader = req.headers.get('Authorization');
    const headers: Record<string, string> = {};
    if (authorizationHeader) {
      headers['Authorization'] = authorizationHeader;
    }

    const backendResponse = await fetch(`${process.env.NEXTAPI_URL}/knowledge_mgmt/knowledge_document/${id}/get_file_link/`, {
      method: 'GET',
      headers
    });

    if (!backendResponse.ok) {
      return NextResponse.json({ message: 'Failed to retrieve file' }, { status: backendResponse.status });
    }

    const fileBuffer = await backendResponse.arrayBuffer();
    const contentType = backendResponse.headers.get('Content-Type') || 'application/octet-stream';

    return new NextResponse(fileBuffer, {
      headers: {
        'Content-Type': contentType,
      },
    });
  } catch (error) {
    console.error('Error fetching file:', error);
    return NextResponse.json({ message: 'Internal Server Error' }, { status: 500 });
  }
};

export const POST = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};

export const PUT = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};

export const DELETE = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};
