import {
  PlatformAccessDeniedError,
  asRecordList,
  fillUrlTemplate,
  mapPlatformApplications,
  mapPlatformMessages,
  mapPlatformSessions,
  parseLlmContextUsageFromEnvelope,
  type LlmContextUsage,
  type PlatformApplication,
  type PlatformContract,
  type PlatformSession,
  unwrapPlatformPayload,
  type Message,
} from '@webchat/core';

export interface PlatformRequestInit {
  apiKey?: string;
  credentials?: RequestCredentials;
  headers?: Record<string, string>;
}

function requestHeaders(init: PlatformRequestInit): HeadersInit {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.headers || {}),
  };
  if (init.apiKey) {
    headers.Authorization = `Bearer ${init.apiKey}`;
  }
  return headers;
}

async function fetchPlatformJson(
  url: string,
  init: PlatformRequestInit,
  extra?: RequestInit
): Promise<unknown> {
  const response = await fetch(url, {
    method: extra?.method ?? 'GET',
    credentials: init.credentials ?? 'include',
    headers: {
      ...requestHeaders(init),
      ...((extra?.headers as Record<string, string>) || {}),
    },
    body: extra?.body,
  });
  if (response.status === 403) {
    throw new PlatformAccessDeniedError();
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    return null;
  }
  return unwrapPlatformPayload(await response.json());
}

export async function fetchPlatformApplications(
  contract: PlatformContract,
  init: PlatformRequestInit
): Promise<PlatformApplication[]> {
  const payload = await fetchPlatformJson(contract.applicationsUrl, init);
  return mapPlatformApplications(asRecordList(payload));
}

export async function fetchPlatformSessions(
  contract: PlatformContract,
  app: Pick<PlatformApplication, 'channelId'>,
  init: PlatformRequestInit
): Promise<PlatformSession[]> {
  const url = fillUrlTemplate(contract.sessionsUrl, {
    channelId: app.channelId,
  });
  const payload = await fetchPlatformJson(url, init);
  return mapPlatformSessions(asRecordList(payload));
}

export async function fetchPlatformMessages(
  contract: PlatformContract,
  sessionId: string,
  init: PlatformRequestInit
): Promise<{ messages: Message[]; usage: LlmContextUsage | null }> {
  const url = fillUrlTemplate(contract.messagesUrl, { sessionId });
  const payload = await fetchPlatformJson(url, init);
  return {
    messages: mapPlatformMessages(asRecordList(payload)),
    usage: parseLlmContextUsageFromEnvelope(payload),
  };
}

export async function deletePlatformSession(
  contract: PlatformContract,
  sessionId: string,
  init: PlatformRequestInit
): Promise<void> {
  if (!contract.deleteSessionUrl || !sessionId) {
    return;
  }
  const url = fillUrlTemplate(contract.deleteSessionUrl, { sessionId });
  await fetchPlatformJson(url, init, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function interruptPlatformChat(
  contract: PlatformContract,
  init: PlatformRequestInit
): Promise<void> {
  if (!contract.interruptUrl) {
    return;
  }
  await fetch(contract.interruptUrl, {
    method: 'POST',
    credentials: init.credentials ?? 'include',
    headers: {
      'Content-Type': 'application/json',
      ...requestHeaders(init),
    },
    body: JSON.stringify({ reason: 'user_manual' }),
  }).catch(() => undefined);
}
