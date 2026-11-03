import { describe, expect, it } from 'vitest';

import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { isComponentSwitchCandidate } from '@/app/ops-analysis/utils/componentParamSwitch';

const param = (queryParams?: Record<string, unknown>): ParamItem => ({
  name: 'group_by',
  alias_name: '排行维度',
  type: 'string',
  value: 'room',
  filterType: 'params',
  inputConfig: {
    control: 'select',
    componentSwitch: true,
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      ...(queryParams ? { queryParams } : {}),
    },
  },
});

describe('component switch with option query refs', () => {
  it('stays available when query params are only literals', () => {
    expect(isComponentSwitchCandidate(param({ room_id: 'fixed' }))).toBe(true);
  });

  it('stays off when a query parameter references another value', () => {
    expect(isComponentSwitchCandidate(param({ room_id: { ref: 'site_id' } }))).toBe(false);
    expect(isComponentSwitchCandidate(param({ room_id: '$site_id$' }))).toBe(false);
  });
});
