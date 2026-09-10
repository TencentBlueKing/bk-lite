import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createImeCompositionTracker,
  isImeCompositionKeyboardEvent,
  shouldSubmitChatOnEnter,
} from '../../packages/webchat-core/src/imeKeyboard';

test('treats composing Enter as IME commit, not send', () => {
  assert.equal(isImeCompositionKeyboardEvent({ key: 'Enter', isComposing: true }), true);
  assert.equal(
    isImeCompositionKeyboardEvent({
      key: 'Enter',
      nativeEvent: { isComposing: true },
    }),
    true,
  );
  assert.equal(isImeCompositionKeyboardEvent({ key: 'Enter', keyCode: 229 }), true);
  assert.equal(
    isImeCompositionKeyboardEvent({
      key: 'Enter',
      nativeEvent: { keyCode: 229 },
    }),
    true,
  );

  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter', isComposing: true }), false);
  assert.equal(
    shouldSubmitChatOnEnter({
      key: 'Enter',
      nativeEvent: { isComposing: true },
    }),
    false,
  );
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter', keyCode: 229 }), false);
});

test('sends on a finished Enter and keeps Shift+Enter as newline', () => {
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter' }), true);
  assert.equal(
    shouldSubmitChatOnEnter({
      key: 'Enter',
      isComposing: false,
      nativeEvent: { isComposing: false, keyCode: 13 },
    }),
    true,
  );
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter', shiftKey: true }), false);
  assert.equal(shouldSubmitChatOnEnter({ key: 'a' }), false);
});

test('ignores the confirming Enter that some IMEs fire after compositionend', async () => {
  const tracker = createImeCompositionTracker();

  tracker.onCompositionStart();
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing()), false);

  tracker.onCompositionEnd();
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing()), false);

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing()), true);

  tracker.dispose();
});

test('keeps composing if a new IME session starts before the end timer', async () => {
  const tracker = createImeCompositionTracker();

  tracker.onCompositionStart();
  tracker.onCompositionEnd();
  tracker.onCompositionStart();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(tracker.isComposing(), true);
  assert.equal(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing()), false);

  tracker.dispose();
});
