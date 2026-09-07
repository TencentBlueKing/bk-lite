import { describe, expect, it } from 'vitest';

import { extractAlarmListItems } from '../listPayload';

describe('extractAlarmListItems', () => {
  it('reads array, items, and results payloads', () => {
    expect(extractAlarmListItems([{ id: 1 }])).toEqual([{ id: 1 }]);
    expect(extractAlarmListItems({ items: [{ id: 2 }] })).toEqual([{ id: 2 }]);
    expect(extractAlarmListItems({ results: [{ id: 3 }] })).toEqual([{ id: 3 }]);
  });

  it('returns an empty list for unknown payloads', () => {
    expect(extractAlarmListItems(null)).toEqual([]);
    expect(extractAlarmListItems({})).toEqual([]);
  });
});
