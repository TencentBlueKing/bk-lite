import assert from 'node:assert/strict';
import { produce } from 'immer';
import { model as modelFixture } from 'src/fixtures/model';
import { INITIAL_SCENE_STATE } from 'src/config';
import { modelSchema } from 'src/schemas/model';
import { updateRectangle } from 'src/stores/reducers/rectangle';
import { updateViewItem } from 'src/stores/reducers/viewItem';

const untouched = modelSchema.safeParse(modelFixture);
assert.equal(untouched.success, true);

const withBinding = produce(modelFixture, (draft) => {
  draft.views[0].items[0].bkBinding = {
    inst_uuid: 'uuid-1',
    model_id: 'host'
  };
  const rectangle = draft.views[0].rectangles?.[0] as
    | { bkBinding?: unknown; bkFollowAlert?: boolean }
    | undefined;

  if (!rectangle) throw new Error('missing rectangle');

  rectangle.bkBinding = { inst_uuid: 'uuid-r', model_id: 'switch' };
  rectangle.bkFollowAlert = true;
});

const parsed = modelSchema.parse(withBinding);

assert.deepEqual(parsed.views[0].items[0].bkBinding, {
  inst_uuid: 'uuid-1',
  model_id: 'host'
});

const withMetrics = produce(modelFixture, (draft) => {
  draft.views[0].items[0].bkDisplayMetrics = {
    mode: 'custom',
    keys: ['os::cpu_usage_total']
  };
  const rectangle = draft.views[0].rectangles?.[0] as { bkDisplayMetrics?: unknown } | undefined;
  if (!rectangle) throw new Error('missing rectangle');
  rectangle.bkDisplayMetrics = { mode: 'cleared' };
});
const parsedMetrics = modelSchema.parse(withMetrics);
assert.deepEqual(parsedMetrics.views[0].items[0].bkDisplayMetrics, {
  mode: 'custom',
  keys: ['os::cpu_usage_total']
});
assert.equal(
  (parsedMetrics.views[0].rectangles?.[0] as { bkDisplayMetrics?: unknown }).bkDisplayMetrics,
  undefined
);

const dropped = produce(modelFixture, (draft) => {
  (draft.views[0].items[0] as { bkDisplayMetrics?: unknown }).bkDisplayMetrics = {
    mode: 'nope'
  };
});
assert.equal(modelSchema.parse(dropped).views[0].items[0].bkDisplayMetrics, undefined);

const cleared = produce(modelFixture, (draft) => {
  (draft.views[0].items[0] as { bkDisplayMetrics?: unknown }).bkDisplayMetrics = {
    mode: 'cleared'
  };
});
assert.equal(modelSchema.parse(cleared).views[0].items[0].bkDisplayMetrics, undefined);
assert.equal(
  (parsed.views[0].rectangles?.[0] as { bkBinding?: unknown }).bkBinding,
  undefined
);
assert.equal('bkBinding' in (parsed.views[0].rectangles?.[0] ?? {}), false);
assert.equal(parsed.views[0].rectangles?.[0].bkFollowAlert, true);

const updatedRectangle = updateRectangle(
  {
    id: parsed.views[0].rectangles?.[0].id ?? '',
    color: parsed.views[0].rectangles?.[0].color
  },
  { viewId: parsed.views[0].id, state: { model: parsed, scene: INITIAL_SCENE_STATE } }
);

assert.equal(
  (updatedRectangle.model.views[0].rectangles?.[0] as { bkBinding?: unknown }).bkBinding,
  undefined
);
assert.equal(
  updatedRectangle.model.views[0].rectangles?.[0].bkFollowAlert,
  true
);

const updatedItem = updateViewItem(
  { id: parsed.views[0].items[0].id, labelHeight: 40 },
  { viewId: parsed.views[0].id, state: updatedRectangle }
);

assert.deepEqual(updatedItem.model.views[0].items[0].bkBinding, {
  inst_uuid: 'uuid-1',
  model_id: 'host'
});

const exported = JSON.parse(JSON.stringify(updatedItem.model));

assert.deepEqual(exported.views[0].items[0].bkBinding, {
  inst_uuid: 'uuid-1',
  model_id: 'host'
});
assert.equal(exported.views[0].rectangles[0].bkFollowAlert, true);
assert.equal(exported.views[0].connectors[0].color, 'color1');

const legacyRectangle = produce(modelFixture, (draft) => {
  const rectangle = draft.views[0].rectangles?.[0] as
    | { bkBinding?: unknown; bkFollowAlert?: boolean }
    | undefined;

  if (!rectangle) throw new Error('missing rectangle');

  rectangle.bkBinding = 'legacy-region-binding';
  rectangle.bkFollowAlert = false;
});

const legacy = modelSchema.safeParse(legacyRectangle);

assert.equal(legacy.success, true);
if (!legacy.success) throw new Error('legacy rectangle should open');
assert.equal(
  (legacy.data.views[0].rectangles?.[0] as { bkBinding?: unknown }).bkBinding,
  undefined
);
assert.equal(legacy.data.views[0].rectangles?.[0].bkFollowAlert, false);

console.log('bkBinding ok');
