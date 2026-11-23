import { describe, expect, it } from 'vitest';

import en from '@/app/rum/locales/en.json';
import zh from '@/app/rum/locales/zh.json';

import {
  addFunnelStepRow,
  blankFunnelStepRows,
  funnelStepPlaceholder,
  funnelStepRowsFromSteps,
  removeFunnelStepRow,
  validateFunnelStepRows,
} from './funnel-step-rows';

describe('funnel step rows', () => {
  it('starts from two blank rows and does not share that array', () => {
    const first = blankFunnelStepRows();
    const second = blankFunnelStepRows();
    expect(first).toEqual(['', '']);
    expect(second).toEqual(['', '']);
    first[0] = '/';
    expect(second).toEqual(['', '']);
  });

  it('adds a blank row and stops at 8', () => {
    const start = ['/a', '/b'];
    const added = addFunnelStepRow(start);
    expect(start).toEqual(['/a', '/b']);
    expect(added).toEqual(['/a', '/b', '']);

    let rows = blankFunnelStepRows();
    for (let i = 0; i < 10; i += 1) rows = addFunnelStepRow(rows);
    expect(rows).toHaveLength(8);
    expect(rows.every((row) => row === '')).toBe(true);

    const nine = Array.from({ length: 9 }, (_, index) => `/s${index}`);
    expect(addFunnelStepRow(nine)).toHaveLength(9);
    expect(addFunnelStepRow(nine)).toEqual(nine);
  });

  it('removes the chosen row and never goes below 2', () => {
    const start = ['/a', '/b', '/c'];
    expect(removeFunnelStepRow(start, 1)).toEqual(['/a', '/c']);
    expect(start).toEqual(['/a', '/b', '/c']);
    expect(removeFunnelStepRow(start, -1)).toEqual(start);
    expect(removeFunnelStepRow(start, 3)).toEqual(start);

    let rows = Array.from({ length: 8 }, (_, index) => `/${index}`);
    while (rows.length > 2) rows = removeFunnelStepRow(rows, rows.length - 1);
    expect(rows).toEqual(['/0', '/1']);
    expect(removeFunnelStepRow(rows, 0)).toEqual(['/0', '/1']);
    expect(removeFunnelStepRow(['/only'], 0)).toEqual(['/only']);
  });

  it('loads an existing 2–8 step funnel without extra blank rows', () => {
    expect(funnelStepRowsFromSteps(['/a', '/b'])).toEqual(['/a', '/b']);
    expect(funnelStepRowsFromSteps(['/', '/checkout', '/success'])).toEqual(['/', '/checkout', '/success']);
    const eight = Array.from({ length: 8 }, (_, index) => `/s${index}`);
    expect(funnelStepRowsFromSteps(eight)).toEqual(eight);
    expect(funnelStepRowsFromSteps(eight)).not.toBe(eight);
    expect(funnelStepRowsFromSteps(undefined)).toEqual(['', '']);
    expect(funnelStepRowsFromSteps(null)).toEqual(['', '']);
    expect(funnelStepRowsFromSteps([])).toEqual(['', '']);
    expect(funnelStepRowsFromSteps(['/only'])).toEqual(['/only', '']);
  });

  it('trims routes and accepts only 2–8 paths that start with /', () => {
    expect(validateFunnelStepRows([' /a ', ' /b '])).toEqual({
      ok: true,
      steps: ['/a', '/b'],
      countError: false,
      invalidIndexes: [],
    });
    const eight = Array.from({ length: 8 }, (_, index) => `/s${index}`);
    const full = validateFunnelStepRows(eight);
    expect(full.ok).toBe(true);
    expect(full.steps).toEqual(eight);

    const withBlank = validateFunnelStepRows(['/a', '   ', '/b']);
    expect(withBlank).toEqual({
      ok: true,
      steps: ['/a', '/b'],
      countError: false,
      invalidIndexes: [],
    });

    const tooFew = validateFunnelStepRows(['/a', '']);
    expect(tooFew.ok).toBe(false);
    expect(tooFew.countError).toBe(true);
    expect(tooFew.steps).toEqual(['/a']);

    expect(validateFunnelStepRows(['', '   '])).toMatchObject({
      ok: false,
      countError: true,
      steps: [],
      invalidIndexes: [],
    });

    const nine = Array.from({ length: 9 }, (_, index) => `/s${index}`);
    expect(validateFunnelStepRows(nine)).toMatchObject({
      ok: false,
      countError: true,
      steps: nine,
    });

    const badPath = validateFunnelStepRows(['checkout', '/pay']);
    expect(badPath).toEqual({
      ok: false,
      steps: ['checkout', '/pay'],
      countError: false,
      invalidIndexes: [0],
    });

    const both = validateFunnelStepRows(['checkout', '']);
    expect(both.ok).toBe(false);
    expect(both.countError).toBe(true);
    expect(both.invalidIndexes).toEqual([0]);

    const source = [' /a ', '/b'];
    validateFunnelStepRows(source);
    expect(source).toEqual([' /a ', '/b']);
  });

  it('uses a single-route placeholder and a per-row hint', () => {
    expect(funnelStepPlaceholder(0)).toBe('/');
    expect(funnelStepPlaceholder(1)).toBe('/checkout');
    expect(funnelStepPlaceholder(4)).toBe('/checkout');
    for (const sample of [funnelStepPlaceholder(0), funnelStepPlaceholder(1), funnelStepPlaceholder(4)]) {
      expect(sample.startsWith('/')).toBe(true);
      expect(sample).not.toContain(',');
    }

    expect(zh.rum.funnels.stepsHint).toBe('每行一个路由，共 2–8 个，每个以 / 开头');
    expect(en.rum.funnels.stepsHint).toBe('One route per row, 2–8 routes, each starting with /');
    expect(zh.rum.funnels.stepsHint).not.toContain('/,/checkout');
    expect(en.rum.funnels.stepsHint).not.toContain('/,/checkout');
    expect(en.rum.funnels.stepsHint.toLowerCase()).not.toContain('comma');
  });
});
