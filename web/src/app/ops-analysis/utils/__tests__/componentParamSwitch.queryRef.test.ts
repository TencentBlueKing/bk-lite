import { describe, expect, it } from 'vitest';

import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { isComponentSwitchCandidate } from '@/app/ops-analysis/utils/componentParamSwitch';
import { preferComponentSwitchLiveValue } from '@/app/ops-analysis/utils/optionsQueryCandidates';
import { resolveOptionsQueryParams } from '@/app/ops-analysis/utils/optionsQueryParamRefs';

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

  it('stays available when a query parameter references another value', () => {
    expect(isComponentSwitchCandidate(param({ room_id: { ref: 'site_id' } }))).toBe(true);
    expect(isComponentSwitchCandidate(param({ room_id: '$site_id$' }))).toBe(true);
  });

  it('uses the live card selection only when the ref names that switch param', () => {
    const saved = 'saved-room';
    const live = ['room-a', 'room-b'];
    const resolved = resolveOptionsQueryParams(
      { group_by: { ref: 'group_by' }, room_id: { ref: 'site_id' } },
      (ref) => preferComponentSwitchLiveValue(
        ref,
        ref === 'group_by' ? saved : 'filter-value',
        { name: 'group_by', value: live },
      ),
    );
    expect(resolved).toEqual({
      blocked: false,
      params: { group_by: live, room_id: 'filter-value' },
      missingRefs: [],
    });
    expect(saved).toBe('saved-room');
  });
});
