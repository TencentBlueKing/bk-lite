import assert from 'node:assert/strict';
import test from 'node:test';
import {
  resolveSingleMainSlotHeight,
  resolveSingleMetaBlockHeight,
  resolveSingleMetaTypography,
  resolveSingleValueMetaLayout,
} from '../singleMetaTypography';

const simulateLayout = (contentAreaHeight: number, scale = 1) => {
  const sparklineHeight = 34;
  const steps: string[] = [];

  for (let i = 0; i < 8; i += 1) {
    const layout = resolveSingleValueMetaLayout({
      contentAreaHeight,
      sparklineHeight,
      scale,
      hasDescription: true,
      hasCompare: true,
    });
    steps.push(
      `${layout.typography.descriptionFontSize}:${layout.typography.compareValueFontSize}:${layout.typography.spacing}:${layout.targetMainFontSize}:${layout.mainSlotHeight}`,
    );
  }

  return steps;
};

test('meta fonts track target main between readable bounds', () => {
  const compact = resolveSingleMetaTypography({
    targetMainFontSize: 40,
    scale: 1,
  });
  const large = resolveSingleMetaTypography({
    targetMainFontSize: 104,
    scale: 1,
  });
  assert.equal(compact.descriptionFontSize, 12);
  assert.equal(compact.compareLabelFontSize, 12);
  assert.equal(compact.compareValueFontSize, 14);
  assert.equal(large.descriptionFontSize, 27.04);
  assert.equal(large.compareLabelFontSize, 18.72);
  assert.equal(large.compareValueFontSize, 22.88);
});

test('unmeasured cards use the readable minimum instead of a fallback main font', () => {
  const layout = resolveSingleValueMetaLayout({
    contentAreaHeight: 0,
    scale: 1,
    hasDescription: true,
  });
  assert.equal(layout.typography.descriptionFontSize, 12);
  assert.equal(layout.typography.compareValueFontSize, 14);
  assert.equal(layout.typography.spacing, 6);
  assert.equal(layout.mainSlotHeight, null);
});

test('screen scale converts visible min and max into canvas pixels', () => {
  const meta = resolveSingleMetaTypography({
    targetMainFontSize: 208,
    scale: 0.5,
  });
  assert.equal(meta.descriptionFontSize, 54.08);
  assert.equal(meta.compareLabelFontSize, 37.44);
  assert.equal(meta.compareValueFontSize, 45.76);
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

test('description stays near a quarter of the height-driven target main', () => {
  const layout = resolveSingleValueMetaLayout({
    contentAreaHeight: 180,
    sparklineHeight: 0,
    scale: 1,
    hasDescription: true,
  });
  const ratio =
    layout.typography.descriptionFontSize / layout.targetMainFontSize;
  assert.ok(ratio >= 0.24 && ratio <= 0.28, `ratio=${ratio}`);
  assert.ok(layout.typography.descriptionFontSize >= 16);
  assert.ok(layout.targetMainFontSize >= 60);
});

test('tall cards keep the main slot close to the value height so it does not sit low', () => {
  const layout = resolveSingleValueMetaLayout({
    contentAreaHeight: 360,
    sparklineHeight: 0,
    scale: 1,
    hasDescription: true,
  });
  assert.ok(layout.mainSlotHeight != null);
  assert.ok((layout.mainSlotHeight ?? 0) <= 113.04 + 0.01);
  assert.ok(
    (layout.mainSlotHeight ?? 0) +
      resolveSingleMetaBlockHeight({
        hasDescription: true,
        hasCompare: false,
        typography: layout.typography,
      }) <
      360,
  );
});

test('same card height keeps meta fonts stable across different main text lengths', () => {
  const a = resolveSingleValueMetaLayout({
    contentAreaHeight: 160,
    hasDescription: true,
  });
  const b = resolveSingleValueMetaLayout({
    contentAreaHeight: 160,
    hasDescription: true,
  });
  // Layout is height-only; digit count never enters the resolver.
  assert.deepEqual(a.typography, b.typography);
  assert.equal(a.targetMainFontSize, b.targetMainFontSize);
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

test('without description the main slot stays unset', () => {
  const layout = resolveSingleValueMetaLayout({
    contentAreaHeight: 200,
    hasDescription: false,
    hasCompare: true,
  });
  assert.equal(layout.mainSlotHeight, null);
  assert.ok(layout.typography.compareValueFontSize >= 14);
});
