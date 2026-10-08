import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DASHBOARD_UNDO_LIMIT,
  cloneDashboardUndoEntry,
  popDashboardUndo,
  pushDashboardUndo,
  recordDashboardEdit,
  redoDashboardEdit,
  undoDashboardEdit,
  type DashboardUndoEntry,
} from '../dashboardAiUndo';

const entry = (name: string): DashboardUndoEntry => ({
  layout: [{ i: name, x: 0, y: 0, w: 4, h: 3, name, valueConfig: { chartType: 'line' } }],
  definitions: [],
  filterValues: {},
  appliedDefinitions: [],
  appliedFilterValues: {},
});

test('undo stack keeps manual and AI edits in order and restores the latest first', () => {
  const first = pushDashboardUndo([], entry('empty'));
  const second = pushDashboardUndo(first, entry('ai'));
  const undone = popDashboardUndo(second);

  assert.equal(undone.entry?.layout[0].name, 'ai');
  assert.equal(popDashboardUndo(undone.stack).entry?.layout[0].name, 'empty');
  assert.equal(popDashboardUndo([]).entry, null);
});

test('a new edit clears redo, and undo then redo walks the same states', () => {
  const recorded = recordDashboardEdit([], entry('before-edit'));
  const undone = undoDashboardEdit(recorded.undo, recorded.redo, entry('after-edit'));
  const redone = redoDashboardEdit(undone.undo, undone.redo, undone.entry!);
  const editedAgain = recordDashboardEdit(redone.undo, entry('after-edit'));

  assert.equal(undone.entry?.layout[0].name, 'before-edit');
  assert.equal(undone.redo[0].layout[0].name, 'after-edit');
  assert.equal(redone.entry?.layout[0].name, 'after-edit');
  assert.equal(editedAgain.redo.length, 0);
  assert.equal(undoDashboardEdit([], [], entry('now')).entry, null);
});

test('undo entries stay isolated from later mutations and the stack is capped', () => {
  const source = entry('kept');
  const stack = pushDashboardUndo([], source);
  source.layout[0].name = 'changed';
  assert.equal(stack[0].layout[0].name, 'kept');

  let capped: DashboardUndoEntry[] = [];
  for (let index = 0; index < DASHBOARD_UNDO_LIMIT + 5; index += 1) {
    capped = pushDashboardUndo(capped, entry(`step-${index}`));
  }
  assert.equal(capped.length, DASHBOARD_UNDO_LIMIT);
  assert.equal(capped[0].layout[0].name, 'step-5');
  assert.deepEqual(cloneDashboardUndoEntry(capped[0]).layout, capped[0].layout);
});
