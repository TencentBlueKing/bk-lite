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
