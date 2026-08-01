import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';

import { validateRecoverySession } from '@/utils/authRecoveryServer';

const noStoreHeaders = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
};

export const GET = async (request: NextRequest) => {
  try {
    const sessionToken = await getToken({ req: request });
    const user = await validateRecoverySession(sessionToken);

    if (!user) {
      return NextResponse.json(
        { authenticated: false },
        { status: 401, headers: noStoreHeaders },
      );
    }

    return NextResponse.json(
      { authenticated: true, user },
      { status: 200, headers: noStoreHeaders },
    );
  } catch (error) {
    console.error('Authentication recovery check failed:', error);
    return NextResponse.json(
      { authenticated: false },
      { status: 401, headers: noStoreHeaders },
    );
  }
};

export const dynamic = 'force-dynamic';
