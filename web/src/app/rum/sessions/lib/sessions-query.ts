export interface SessionsListQueryInput {
  range: string;
  orderBy: string;
  pageNo: number;
  pageSize: number;
  traffic: string;
  application: string;
  sessionId: string;
  userId: string;
  hasError: boolean;
  hasReplay: boolean;
  route: string;
}

/** Query string shared by the sessions list and its trend. Blank ids are omitted. */
export function buildSessionsListQuery(input: SessionsListQueryInput): Record<string, string> {
  const sessionId = input.sessionId.trim();
  const userId = input.userId.trim();
  const out: Record<string, string> = {
    range: input.range,
    orderBy: input.orderBy,
    limit: String(input.pageSize),
    offset: String((input.pageNo - 1) * input.pageSize),
    traffic: input.traffic,
  };
  if (input.application) out.application = input.application;
  if (sessionId) out.sessionId = sessionId;
  if (userId) out.userId = userId;
  if (input.hasError) out.hasError = '1';
  if (input.hasReplay) out.hasReplay = '1';
  if (input.route) out.route = input.route;
  return out;
}
