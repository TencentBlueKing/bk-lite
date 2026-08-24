import assert from 'node:assert/strict';
import test from 'node:test';
import {
  resolveSingleMainSlotHeight,
  resolveSingleMetaBlockHeight,
  resolveSingleMetaTypography,
  SINGLE_META_TYPOGRAPHY,
} from '../singleMetaTypography';

const simulateLayout = (contentAreaHeight: number, scale = 1) => {
  const sparklineHeight = 34;
  const steps: string[] = [];
  let mainFontSize = 36;

  for (let i = 0; i < 8; i += 1) {
    const meta = resolveSingleMetaTypography({ contentAreaHeight, scale });
    const descriptionReserve =
      meta.descriptionFontSize *
        SINGLE_META_TYPOGRAPHY.descriptionLineHeight *
        SINGLE_META_TYPOGRAPHY.descriptionMaxLines +
      meta.spacing;
    const compareReserve =
      meta.compareValueFontSize * SINGLE_META_TYPOGRAPHY.compareLineHeight +
      meta.spacing;
    const remaining =
      contentAreaHeight - descriptionReserve - compareReserve - sparklineHeight;
    mainFontSize = Math.max(18, Math.min(104, remaining * 0.7));
    steps.push(
      `${meta.descriptionFontSize}:${meta.compareValueFontSize}:${meta.spacing}:${mainFontSize.toFixed(2)}`,
    );
  }

  return steps;
};

test('meta fonts scale with card height between readable bounds', () => {
  const compact = resolveSingleMetaTypography({
    contentAreaHeight: 120,
    scale: 1,
  });
  const large = resolveSingleMetaTypography({
    contentAreaHeight: 360,
    scale: 1,
  });
  assert.equal(compact.descriptionFontSize, 12);
  assert.equal(compact.compareLabelFontSize, 12);
  assert.equal(compact.compareValueFontSize, 14);
  assert.equal(large.descriptionFontSize, 22);
  assert.equal(large.compareLabelFontSize, 20);
  assert.equal(large.compareValueFontSize, 24);
});

test('unmeasured cards use the readable minimum instead of a fallback main font', () => {
  const meta = resolveSingleMetaTypography({ contentAreaHeight: 0, scale: 1 });
  assert.equal(meta.descriptionFontSize, 12);
  assert.equal(meta.compareValueFontSize, 14);
  assert.equal(meta.spacing, 6);
});

test('screen scale converts visible min and max into canvas pixels', () => {
  const meta = resolveSingleMetaTypography({
    contentAreaHeight: 600,
    scale: 0.5,
  });
  assert.equal(meta.descriptionFontSize, 44);
  assert.equal(meta.compareLabelFontSize, 40);
  assert.equal(meta.compareValueFontSize, 48);
});

test('layout does not chase fitted main font across typical card heights', () => {
  for (let height = 80; height <= 400; height += 1) {
    const steps = simulateLayout(height);
    assert.equal(
      new Set(steps).size,
      1,
      `card height ${height} oscillated: ${steps.join(' -> ')}`,
    );
  }
});

test('tall cards keep the main slot close to the value height so it does not sit low', () => {
  const typography = resolveSingleMetaTypography({
    contentAreaHeight: 360,
    scale: 1,
  });
  const descriptionBlockHeight = resolveSingleMetaBlockHeight({
    hasDescription: true,
    hasCompare: false,
    typography,
  });
  const slot = resolveSingleMainSlotHeight({
    contentAreaHeight: 360,
    metaBlockHeight: descriptionBlockHeight,
    sparklineHeight: 0,
    scale: 1,
  });
  assert.equal(slot, 113.04);
  assert.ok((slot ?? 0) < 140);
  assert.ok((slot ?? 0) + descriptionBlockHeight < 360);
});

test('unmeasured cards leave the main slot unset so layout can fill first', () => {
  assert.equal(
    resolveSingleMainSlotHeight({
      contentAreaHeight: 0,
      metaBlockHeight: 40,
      sparklineHeight: 0,
    }),
    null,
  );
});
