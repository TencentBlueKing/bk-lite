import assert from 'node:assert/strict';
import test from 'node:test';

import React, { useEffect } from 'react';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { StateMachine } from '../packages/webchat-core/src/stateMachine';
import { useLatestChatStateCallback } from '../packages/webchat-ui/src/chatStateCallback';

type StateChangeCallback = (state: string) => void;

function ChatStateListener({
  stateMachine,
  onStateChange,
}: {
  stateMachine: StateMachine;
  onStateChange?: StateChangeCallback;
}) {
  const callbackRef = useLatestChatStateCallback(onStateChange);

  useEffect(
    () => stateMachine.on((event) => callbackRef.current?.(event.to)),
    [callbackRef, stateMachine]
  );
  return null;
}

test('rerendered listener dispatches state-machine events only to the latest callback', () => {
  const initialStates: string[] = [];
  const latestStates: string[] = [];
  const stateMachine = new StateMachine('idle');
  let renderer: ReactTestRenderer;

  act(() => {
    renderer = create(
      React.createElement(ChatStateListener, {
        stateMachine,
        onStateChange: (state) => initialStates.push(state),
      })
    );
  });
  act(() => {
    stateMachine.transition('connecting');
  });
  act(() => {
    renderer.update(
      React.createElement(ChatStateListener, {
        stateMachine,
        onStateChange: (state) => latestStates.push(state),
      })
    );
  });
  act(() => {
    stateMachine.transition('connected');
  });
  act(() => renderer.unmount());
  stateMachine.transition('chatting');

  assert.deepEqual(initialStates, ['connecting']);
  assert.deepEqual(latestStates, ['connected']);
});

test('removing the callback stops later state notifications', () => {
  const states: string[] = [];
  const stateMachine = new StateMachine('idle');
  let renderer: ReactTestRenderer;

  act(() => {
    renderer = create(
      React.createElement(ChatStateListener, {
        stateMachine,
        onStateChange: (state) => states.push(state),
      })
    );
  });
  act(() => {
    renderer.update(React.createElement(ChatStateListener, { stateMachine }));
  });
  act(() => {
    stateMachine.transition('connecting');
  });
  act(() => renderer.unmount());

  assert.deepEqual(states, []);
});
