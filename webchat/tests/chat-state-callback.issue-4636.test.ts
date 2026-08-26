import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { SessionManager, StateMachine } from '@webchat/core';
import { Chat } from '../packages/webchat-ui/src/Chat';
import { FloatingButton } from '../packages/webchat-ui/src/FloatingButton';

const documentStub = {
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
};
Object.defineProperty(globalThis, 'document', { configurable: true, value: documentStub });

function captureMountedStateMachine() {
  let mountedStateMachine: StateMachine | undefined;
  let subscriptionCount = 0;
  const recordStateMachine = (stateMachine: StateMachine) => {
    mountedStateMachine = stateMachine;
  };
  const originalOn = StateMachine.prototype.on;
  StateMachine.prototype.on = function capture(listener) {
    recordStateMachine(this);
    subscriptionCount += 1;
    return originalOn.call(this, listener);
  };

  return {
    get: () => {
      assert.ok(mountedStateMachine, 'the production Chat must subscribe to its StateMachine');
      return mountedStateMachine;
    },
    subscriptionCount: () => subscriptionCount,
    restore: () => {
      StateMachine.prototype.on = originalOn;
    },
  };
}

test('Chat dispatches state events only to the latest callback and stops after unmount', () => {
  const initialStates: string[] = [];
  const latestStates: string[] = [];
  const captured = captureMountedStateMachine();
  let renderer: ReactTestRenderer;

  try {
    act(() => {
      renderer = create(
        React.createElement(Chat, {
          enableStorage: false,
          onStateChange: (state) => initialStates.push(state),
        })
      );
    });
    const stateMachine = captured.get();
    act(() => {
      stateMachine.transition('connecting');
    });
    act(() => {
      renderer.update(
        React.createElement(Chat, {
          enableStorage: false,
          onStateChange: (state) => latestStates.push(state),
        })
      );
    });
    assert.equal(captured.subscriptionCount(), 1);
    act(() => {
      stateMachine.transition('connected');
    });
    act(() => renderer.update(React.createElement(Chat, { enableStorage: false })));
    act(() => {
      stateMachine.transition('chatting');
    });
    act(() => renderer.unmount());
    stateMachine.transition('connected');

    assert.deepEqual(initialStates, ['connecting']);
    assert.deepEqual(latestStates, ['connected']);
  } finally {
    captured.restore();
  }
});

test('Chat commits the latest callback before passive effects run', () => {
  const initialStates: string[] = [];
  const latestStates: string[] = [];
  const captured = captureMountedStateMachine();
  let renderer: ReactTestRenderer;

  try {
    act(() => {
      renderer = create(
        React.createElement(Chat, {
          enableStorage: false,
          onStateChange: (state) => initialStates.push(state),
        })
      );
    });
    const stateMachine = captured.get();

    renderer.update(
      React.createElement(Chat, {
        enableStorage: false,
        onStateChange: (state) => latestStates.push(state),
      })
    );
    stateMachine.transition('connecting');

    assert.deepEqual(initialStates, []);
    assert.deepEqual(latestStates, ['connecting']);
    act(() => renderer.unmount());
  } finally {
    captured.restore();
  }
});

test('FloatingButton supports the legacy callback without the standard callback', async () => {
  const legacyStates: string[] = [];
  const captured = captureMountedStateMachine();
  let renderer: ReactTestRenderer;

  try {
    act(() => {
      renderer = create(
        React.createElement(FloatingButton, {
          enableStorage: false,
          onChatStateChange: (state) => legacyStates.push(state),
        })
      );
    });
    await act(async () => {
      renderer.root.findByType('button').props.onClick();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const stateMachine = captured.get();
    act(() => {
      stateMachine.transition('connecting');
    });
    act(() => renderer.unmount());

    assert.deepEqual(legacyStates, ['connecting']);
  } finally {
    captured.restore();
  }
});

test('FloatingButton keeps standard and legacy callback compatibility across rerenders', async () => {
  const standardStates: string[] = [];
  const legacyStates: string[] = [];
  const captured = captureMountedStateMachine();
  let renderer: ReactTestRenderer;

  try {
    act(() => {
      renderer = create(
        React.createElement(FloatingButton, {
          enableStorage: false,
          onStateChange: (state) => standardStates.push(state),
        })
      );
    });
    await act(async () => {
      renderer.root.findByType('button').props.onClick();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const stateMachine = captured.get();
    act(() => {
      stateMachine.transition('connecting');
    });
    act(() => {
      renderer.update(
        React.createElement(FloatingButton, {
          enableStorage: false,
          onStateChange: (state) => standardStates.push(`fallback:${state}`),
          onChatStateChange: (state) => legacyStates.push(state),
        })
      );
    });
    assert.equal(captured.subscriptionCount(), 1);
    act(() => {
      stateMachine.transition('connected');
    });
    act(() => {
      renderer.update(React.createElement(FloatingButton, { enableStorage: false }));
    });
    act(() => {
      stateMachine.transition('chatting');
    });
    act(() => renderer.unmount());
    stateMachine.transition('connected');

    assert.deepEqual(standardStates, ['connecting']);
    assert.deepEqual(legacyStates, ['connected']);
  } finally {
    captured.restore();
  }
});

test('Chat reinitializes scoped session storage when scope changes without unmounting', () => {
  const storageKeys: string[] = [];
  const originalInitSession = SessionManager.prototype.initSession;
  SessionManager.prototype.initSession = function captureStorageKey(userId?: string) {
    storageKeys.push((this as unknown as { storageKey: string }).storageKey);
    return originalInitSession.call(this, userId);
  };
  let renderer: ReactTestRenderer;

  try {
    act(() => {
      renderer = create(React.createElement(Chat, { enableStorage: false, storageScope: 'alice' }));
    });
    act(() => {
      renderer.update(React.createElement(Chat, { enableStorage: false, storageScope: 'bob' }));
    });
    assert.deepEqual(storageKeys, ['webchat_session:v2:alice', 'webchat_session:v2:bob']);
    act(() => renderer.unmount());
  } finally {
    SessionManager.prototype.initSession = originalInitSession;
  }
});
