import assert from 'node:assert/strict';
import test from 'node:test';

import {
  readInteractionRuntime,
  resetInteractionRuntime,
  setInteractionRuntime,
} from '@/app/ops-analysis/context/interactionRuntime';
import { shouldNavigateInteraction } from '@/app/ops-analysis/utils/interactionLink';

const snapshot = (surface: 'edit' | 'view' | 'share') => ({
  surface,
  definitions: [],
  values: {},
});

test('runtime defaults to a surface that does not navigate and cleanup keeps the other owner', () => {
  resetInteractionRuntime();
  const initial = readInteractionRuntime();
  assert.equal(initial.surface, 'edit');
  assert.equal(shouldNavigateInteraction(initial.surface), false);

  setInteractionRuntime(snapshot('view'), 'canvas-a');
  setInteractionRuntime(snapshot('share'), 'canvas-b');
  assert.equal(readInteractionRuntime().surface, 'share');

  resetInteractionRuntime('canvas-b');
  assert.equal(readInteractionRuntime().surface, 'view');

  resetInteractionRuntime('canvas-gone');
  assert.equal(readInteractionRuntime().surface, 'view');

  resetInteractionRuntime('canvas-a');
  assert.equal(readInteractionRuntime().surface, 'edit');
  assert.equal(shouldNavigateInteraction(readInteractionRuntime().surface), false);
});
