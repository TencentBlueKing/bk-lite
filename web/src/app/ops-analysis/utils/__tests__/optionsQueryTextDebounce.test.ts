import { describe, expect, it } from 'vitest';

import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  OPTIONS_QUERY_TEXT_DEBOUNCE_MS,
  isFreeTextOptionsFilter,
  isFreeTextOptionsParam,
  isOptionsQueryTextEmpty,
} from '@/app/ops-analysis/utils/optionsQueryTextDebounce';

const param = (patch: Partial<ParamItem>): ParamItem => ({
  name: 'room_id',
  alias_name: '机房',
  type: 'string',
  value: null,
  ...patch,
});

const filter = (
  patch: Partial<UnifiedFilterDefinition>,
): UnifiedFilterDefinition => ({
  id: 'room',
  key: 'room_id',
  name: '机房',
  type: 'string',
  order: 0,
  enabled: true,
  ...patch,
});

describe('options query text debounce classification', () => {
  it('waits 300ms and treats only blank text as immediately empty', () => {
    expect(OPTIONS_QUERY_TEXT_DEBOUNCE_MS).toBe(300);
    expect(isOptionsQueryTextEmpty(null)).toBe(true);
    expect(isOptionsQueryTextEmpty(undefined)).toBe(true);
    expect(isOptionsQueryTextEmpty('')).toBe(true);
    expect(isOptionsQueryTextEmpty('0')).toBe(false);
    expect(isOptionsQueryTextEmpty(0)).toBe(false);
    expect(isOptionsQueryTextEmpty(false)).toBe(false);
  });

  it('marks plain text, textarea and number params as free text', () => {
    expect(isFreeTextOptionsParam(param({ type: 'string' }))).toBe(true);
    expect(isFreeTextOptionsParam(param({ name: 'query', type: 'string' }))).toBe(true);
    expect(isFreeTextOptionsParam(param({ type: 'number' }))).toBe(true);
    expect(isFreeTextOptionsParam(param({
      inputConfig: { control: 'input' },
    }))).toBe(true);
  });

  it('leaves select, radio, organization and legacy option lists immediate', () => {
    expect(isFreeTextOptionsParam(param({
      inputConfig: {
        control: 'select',
        optionsSource: { type: 'static', staticItems: [] },
      },
    }))).toBe(false);
    expect(isFreeTextOptionsParam(param({
      inputConfig: {
        control: 'radio',
        optionsSource: { type: 'static', staticItems: [{ label: '一区', value: 'a1' }] },
      },
    }))).toBe(false);
    expect(isFreeTextOptionsParam(param({ inputMode: 'organization' }))).toBe(false);
    expect(isFreeTextOptionsParam(param({
      options: [{ label: '东', value: 'east' }],
    }))).toBe(false);
    expect(isFreeTextOptionsParam(param({ type: 'boolean' }))).toBe(false);
    expect(isFreeTextOptionsParam(param({ type: 'date' }))).toBe(false);
  });

  it('marks filter text and number as free text, and selections as immediate', () => {
    expect(isFreeTextOptionsFilter(filter({ type: 'string' }))).toBe(true);
    expect(isFreeTextOptionsFilter(filter({ type: 'number' }))).toBe(true);
    expect(isFreeTextOptionsFilter(filter({
      inputConfig: { control: 'input' },
    }))).toBe(true);
    expect(isFreeTextOptionsFilter(filter({
      inputConfig: {
        control: 'select',
        optionsSource: { type: 'static', staticItems: [] },
      },
    }))).toBe(false);
    expect(isFreeTextOptionsFilter(filter({ inputMode: 'radio' }))).toBe(false);
    expect(isFreeTextOptionsFilter(filter({ inputMode: 'organization' }))).toBe(false);
    expect(isFreeTextOptionsFilter(filter({ type: 'timeRange' }))).toBe(false);
    expect(isFreeTextOptionsFilter(filter({ type: 'dateRange' }))).toBe(false);
  });
});
