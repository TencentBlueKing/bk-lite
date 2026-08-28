import assert from 'node:assert/strict';
import test from 'node:test';

import { SessionManager } from '../../packages/webchat-core/src/sessionManager';
import type { ChatSession } from '../../packages/webchat-core/src/types';

const DAY_IN_MS = 24 * 60 * 60 * 1000;

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

/** Install a localStorage stub and return a function that restores the original. */
function installLocalStorage(storage: Storage): () => void {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storage,
  });

  return () => {
    if (previous) {
      Object.defineProperty(globalThis, 'localStorage', previous);
    } else {
      Reflect.deleteProperty(globalThis, 'localStorage');
    }
  };
}

/** Build the persisted session fixture for a given activity timestamp. */
function storedSession(lastActivityTime: number): ChatSession {
  return {
    sessionId: 'persisted-session',
    messages: [],
    startTime: lastActivityTime,
    lastActivityTime,
  };
}

test('restores a persisted session that is less than 24 hours old', () => {
  const now = 1_800_000_000_000;
  const storage = new MemoryStorage();
  storage.setItem('@webchat/session', JSON.stringify(storedSession(now - DAY_IN_MS + 1)));

  const restoreStorage = installLocalStorage(storage);
  const originalNow = Date.now;
  Date.now = () => now;

  try {
    const session = new SessionManager({ enableStorage: true }).initSession();
    assert.equal(session.sessionId, 'persisted-session');
  } finally {
    Date.now = originalNow;
    restoreStorage();
  }
});

test('expires a persisted session at the exact 24-hour boundary', () => {
  const now = 1_800_000_000_000;
  const storage = new MemoryStorage();
  storage.setItem('@webchat/session', JSON.stringify(storedSession(now - DAY_IN_MS)));

  const restoreStorage = installLocalStorage(storage);
  const originalNow = Date.now;
  Date.now = () => now;

  try {
    const session = new SessionManager({ enableStorage: true }).initSession();
    assert.notEqual(session.sessionId, 'persisted-session');
    assert.equal(session.startTime, now);
  } finally {
    Date.now = originalNow;
    restoreStorage();
  }
});

test('restores only the session stored under the same owner and endpoint scope', () => {
  const storage = new MemoryStorage();
  const restoreStorage = installLocalStorage(storage);

  try {
    const alice = new SessionManager({
      enableStorage: true,
      storageScope: 'alice|https://chat.example.com/sse',
    });
    const aliceSession = alice.initSession('alice');
    alice.addMessage({
      id: 'secret-message',
      type: 'text',
      content: 'alice only',
      sender: 'user',
      timestamp: Date.now(),
    });

    const restoredAlice = new SessionManager({
      enableStorage: true,
      storageScope: 'alice|https://chat.example.com/sse',
    }).initSession('alice');
    assert.equal(restoredAlice.sessionId, aliceSession.sessionId);
    assert.equal(restoredAlice.messages[0]?.id, 'secret-message');

    const bob = new SessionManager({
      enableStorage: true,
      storageScope: 'bob|https://chat.example.com/sse',
    }).initSession('bob');
    assert.notEqual(bob.sessionId, aliceSession.sessionId);
    assert.deepEqual(bob.messages, []);

    const otherEndpoint = new SessionManager({
      enableStorage: true,
      storageScope: 'alice|https://other.example.com/sse',
    }).initSession('alice');
    assert.notEqual(otherEndpoint.sessionId, aliceSession.sessionId);
    assert.deepEqual(otherEndpoint.messages, []);
  } finally {
    restoreStorage();
  }
});

test('scoped storage rejects malformed recent JSON instead of restoring it as a session', () => {
  const storage = new MemoryStorage();
  storage.setItem(
    '@webchat/session:v2:alice%7Chttps%3A%2F%2Fchat.example.com%2Fsse',
    JSON.stringify({ lastActivityTime: Date.now(), messages: 'not-an-array' }),
  );
  const restoreStorage = installLocalStorage(storage);

  try {
    const session = new SessionManager({
      enableStorage: true,
      storageScope: 'alice|https://chat.example.com/sse',
    }).initSession('alice');
    assert.equal(session.userId, 'alice');
    assert.deepEqual(session.messages, []);
    assert.notEqual(session.sessionId, undefined);
  } finally {
    restoreStorage();
  }
});
