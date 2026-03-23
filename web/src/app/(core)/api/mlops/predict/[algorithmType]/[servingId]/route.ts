import { NextRequest } from 'next/server';

import { forwardMlopsRequest } from '../../../_utils';

interface RouteContext {
  params: Promise<{
    algorithmType: string;
    servingId: string;
  }>;
}

export const POST = async (req: NextRequest, { params }: RouteContext) => {
  const { algorithmType, servingId } = await params;

  return forwardMlopsRequest(req, `/${algorithmType}_servings/${servingId}/predict/`);
};
