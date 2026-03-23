import { NextRequest } from 'next/server';

import { forwardMlopsRequest } from '../../_utils';

interface RouteContext {
  params: Promise<{
    algorithmType: string;
  }>;
}

export const GET = async (req: NextRequest, { params }: RouteContext) => {
  const { algorithmType } = await params;

  return forwardMlopsRequest(req, `/${algorithmType}_servings/`);
};
