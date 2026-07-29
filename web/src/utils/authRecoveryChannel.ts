const AUTH_RECOVERY_CHANNEL = 'bk-lite:auth-recovery';
const AUTH_RECOVERY_STORAGE_KEY = 'bk-lite:auth-recovery-event';
const AUTH_RECOVERY_PROTOCOL_VERSION = 1;

export interface AuthRecoveryEvent {
  type: 'auth-recovered';
  version: typeof AUTH_RECOVERY_PROTOCOL_VERSION;
  eventId: string;
  occurredAt: number;
}

const createEventId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
};
export const createAuthRecoveryEvent = (): AuthRecoveryEvent => ({
  type: 'auth-recovered',
  version: AUTH_RECOVERY_PROTOCOL_VERSION,
  eventId: createEventId(),
  occurredAt: Date.now(),
});

export const isAuthRecoveryEvent = (value: unknown): value is AuthRecoveryEvent => {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const event = value as Partial<AuthRecoveryEvent>;
  return event.type === 'auth-recovered'
    && event.version === AUTH_RECOVERY_PROTOCOL_VERSION
    && typeof event.eventId === 'string'
    && event.eventId.length > 0
    && typeof event.occurredAt === 'number'
    && Number.isFinite(event.occurredAt);
};

export const publishAuthRecovery = (
  event: AuthRecoveryEvent = createAuthRecoveryEvent(),
): AuthRecoveryEvent => {
  if (typeof window === 'undefined') {
    return event;
  }

  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(AUTH_RECOVERY_CHANNEL);
    channel.postMessage(event);
    channel.close();
    return event;
  }

  try {
    window.localStorage.setItem(AUTH_RECOVERY_STORAGE_KEY, JSON.stringify(event));
  } catch {
    // The initiating window still completes its local recovery when storage is unavailable.
  }

  return event;
};

export const subscribeAuthRecovery = (
  handler: (event: AuthRecoveryEvent) => void,
): (() => void) => {
  if (typeof window === 'undefined') {
    return () => undefined;
  }

  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(AUTH_RECOVERY_CHANNEL);
    const handleMessage = (messageEvent: MessageEvent<unknown>) => {
      if (isAuthRecoveryEvent(messageEvent.data)) {
        handler(messageEvent.data);
      }
    };

    channel.addEventListener('message', handleMessage);
    return () => {
      channel.removeEventListener('message', handleMessage);
      channel.close();
    };
  }

  const handleStorage = (storageEvent: StorageEvent) => {
    if (storageEvent.key !== AUTH_RECOVERY_STORAGE_KEY || !storageEvent.newValue) {
      return;
    }

    try {
      const event = JSON.parse(storageEvent.newValue);
      if (isAuthRecoveryEvent(event)) {
        handler(event);
      }
    } catch {
      // Ignore malformed events written by unrelated or older clients.
    }
  };

  window.addEventListener('storage', handleStorage);
  return () => window.removeEventListener('storage', handleStorage);
};
