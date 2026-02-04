// @ts-expect-error - next-auth v4 getToken exists but types may not be exported correctly
import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';

// Handle the actual logout API
export const POST = async (req: NextRequest) => {
  try {

    // Attempt to get the JWT from the request
    const token = await getToken({ req });
    if (!token) {
      console.warn('No token found in the session.');
      return NextResponse.json(
        { message: 'No session found', error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Additional server-side cleanup logic can be added here
    // For example: notify other services about user logout, log events, etc.

    // Return success
    return NextResponse.json({ 
      success: true, 
      message: 'Logout successful'
    }, { status: 200 });
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
