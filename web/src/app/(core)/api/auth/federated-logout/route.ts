// @ts-expect-error - next-auth v4 getToken exists but types may not be exported correctly
import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';

// Handle the actual logout API
export const POST = async (req: NextRequest) => {
  try {
    // Attempt to get the JWT from the request
    const token = await getToken({ req });
    if (!token) {
      return NextResponse.json(
        { message: 'No session found', error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Revoke the backend token via the logout API
    const bkliteToken = (token as Record<string, unknown>).token as string | undefined;
    const apiUrl = process.env.NEXTAPI_URL;
    if (bkliteToken && apiUrl) {
      try {
        const url = new URL('/api/v1/core/api/logout/', apiUrl);
        await fetch(url.toString(), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: bkliteToken }),
        });
      } catch (revokeError) {
        console.error('Token revocation failed (non-blocking):', revokeError);
      }
    }

    // Return success with Set-Cookie to clear bklite_token
    const response = NextResponse.json({ 
      success: true, 
      message: 'Logout successful'
    }, { status: 200 });

    response.cookies.delete({
      name: 'bklite_token',
      path: '/',
    });

    return response;
  } catch (error) {
    console.error('Logout error:', error);
    return NextResponse.json(
      { message: 'Logout processing failed' },
      { status: 500 }
    );
  }
};

// Optional: Handle GET requests for debugging or consistency
export const GET = async () => {
  return NextResponse.json({ 
    success: true, 
    url: '/auth/signin' 
  }, { status: 200 });
};

// Export to force dynamic behavior
export const dynamic = 'force-dynamic';
