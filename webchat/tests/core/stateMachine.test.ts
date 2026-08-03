import assert from 'node:assert/strict';
import test from 'node:test';

import { StateMachine } from '../../packages/webchat-core/src/stateMachine';
import type { StateChangeEvent } from '../../packages/webchat-core/src/types';

test('moves an idle session through every legal state before chatting', () => {
  const machine = new StateMachine();
  const transitions: Array<[string, string]> = [];

  machine.on((event: StateChangeEvent) => {
    transitions.push([event.from, event.to]);
  });

  assert.equal(machine.transitionToChatting(), true);
  assert.equal(machine.getState(), 'chatting');
  assert.deepEqual(transitions, [
    ['idle', 'connecting'],
    ['connecting', 'connected'],
    ['connected', 'chatting'],
  ]);
});

test('rejects a direct idle-to-chatting transition', () => {
  const machine = new StateMachine();
  const originalWarn = console.warn;
  console.warn = () => undefined;

  try {
    assert.equal(machine.transition('chatting'), false);
    assert.equal(machine.getState(), 'idle');
  } finally {
    console.warn = originalWarn;
  }
});
