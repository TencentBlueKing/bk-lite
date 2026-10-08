import { describe, expect, it } from 'vitest';

import { buildFiltersFromDashboardLayout } from '../useDashboardLayoutSync';
import { isOrganizationFilterDefinition } from '@/app/ops-analysis/utils/unifiedFilterState';
import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';

describe('prepared widget params become dashboard filters', () => {
  it('keeps the organization control and turns a numeric time default into a relative range', () => {
    const layout: DashboardLayoutItem[] = [
      {
        i: 'card-1',
        x: 0,
        y: 0,
        w: 6,
        h: 4,
        name: '资产',
        valueConfig: {
          chartType: 'single',
          dataSource: 2,
          selectedFields: ['value'],
          dataSourceParams: [
            {
              name: 'organization',
              alias_name: '组织',
              type: 'string',
              filterType: 'filter',
              value: null,
              inputConfig: { control: 'organization' },
            },
            {
              name: 'time',
              alias_name: '时间',
              type: 'timeRange',
              filterType: 'filter',
              value: 60,
            },
          ],
        },
      },
    ];

    const filters = buildFiltersFromDashboardLayout({
      layout,
      previousDefinitions: [],
      dataSources: [],
    });
    const organization = filters.find((item) => item.key === 'organization');
    const time = filters.find((item) => item.key === 'time');

    expect(organization && isOrganizationFilterDefinition(organization)).toBe(true);
    expect(time?.type).toBe('timeRange');
    expect(time?.defaultValue).toMatchObject({ selectValue: 60 });
  });
});
