import { describe, expect, it } from 'vitest';

import type { ChangeRecord } from '../changeRecordTypes';
import {
  DEFAULT_SCENARIOS,
  filterChangeRecordsByScenarios,
  getChangeRecordRelationInfo,
  groupChangeRecordsByMonth,
} from '../changeRecordView';

function record(partial: Partial<ChangeRecord> & { id: number | string }): ChangeRecord {
  return {
    model_id: 'host',
    label: 'instance',
    type: 'update',
    scenario: 'ordinary_attribute_change',
    operator: 'admin',
    created_at: '2026-08-25 18:00:00',
    ...partial,
  };
}

describe('groupChangeRecordsByMonth', () => {
  it('groups records by YYYY-MM and keeps newest first within a month', () => {
    expect(
      groupChangeRecordsByMonth([
        record({ id: 1, created_at: '2026-08-25 18:02:16' }),
        record({ id: 2, created_at: '2026-08-25 18:00:20' }),
        record({ id: 3, created_at: '2026-09-01 10:00:00' }),
      ]).map((group) => ({
        month: group.month,
        count: group.count,
        ids: group.list.map((item) => item.id),
      })),
    ).toEqual([
      { month: '2026-09', count: 1, ids: [3] },
      { month: '2026-08', count: 2, ids: [1, 2] },
    ]);
  });
});

describe('filterChangeRecordsByScenarios', () => {
  it('keeps the default high-signal subset and passes through when no filter is set', () => {
    const records = [
      record({ id: 1, scenario: 'ordinary_attribute_change' }),
      record({ id: 2, scenario: 'collect_automation_change' }),
      record({ id: 3, scenario: 'relation_change' }),
    ];
    expect(
      filterChangeRecordsByScenarios(records, DEFAULT_SCENARIOS).map((item) => item.id),
    ).toEqual([1, 3]);
    expect(filterChangeRecordsByScenarios(records, []).map((item) => item.id)).toEqual([
      1, 2, 3,
    ]);
  });
});

describe('getChangeRecordRelationInfo', () => {
  it('reads add/remove relation endpoints from the frozen edge payload', () => {
    expect(
      getChangeRecordRelationInfo(
        record({
          id: 11,
          label: 'instance_association',
          type: 'create_edge',
          after_data: {
            edge: { src_model_id: 'application', dst_model_id: 'host' },
            src: { inst_name: 'app-1' },
            dst: { inst_name: 'host-01' },
          },
        }),
      ),
    ).toEqual({
      kind: 'add',
      src: 'app-1',
      dst: 'host-01',
      srcModel: 'application',
      dstModel: 'host',
    });
    expect(
      getChangeRecordRelationInfo(
        record({
          id: 12,
          label: 'instance_association',
          type: 'delete_edge',
          before_data: {
            edge: { src_model_id: 'application', dst_model_id: 'host' },
            src: { inst_name: 'app-1' },
            dst: { inst_name: 'host-01' },
          },
        }),
      )?.kind,
    ).toBe('remove');
    expect(getChangeRecordRelationInfo(record({ id: 13, label: 'instance' }))).toBeNull();
  });
});
