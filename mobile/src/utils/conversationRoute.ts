interface ConversationRouteParams {
  botId: string | number;
  sessionId?: string;
  nodeId?: string;
}

interface ConversationApplicationIdentity {
  node_id: string;
}

export function selectConversationApplication<T extends ConversationApplicationIdentity>(
  applications: T[],
  requestedNodeId?: string | null,
): T | undefined {
  if (requestedNodeId) {
    return applications.find((application) => application.node_id === requestedNodeId);
  }

  return applications.length === 1 ? applications[0] : undefined;
}

export function buildConversationHref({
  botId,
  sessionId,
  nodeId,
}: ConversationRouteParams): string {
  const params = new URLSearchParams({ bot_id: String(botId) });
  if (sessionId) params.set('session_id', sessionId);
  if (nodeId) params.set('node_id', nodeId);
  return `/conversation?${params.toString()}`;
}
