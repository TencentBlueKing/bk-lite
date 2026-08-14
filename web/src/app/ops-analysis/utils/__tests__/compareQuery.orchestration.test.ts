import { describe, expect, it } from 'vitest';

import { fetchCompareData } from '@/app/ops-analysis/utils/compareQuery';
import { RuntimeRequestCancelledError } from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

describe('compare query orchestration validity', () => {
  it('does not start baseline after the orchestration becomes stale', async () => {
    let valid = true;
    const startedParams: unknown[] = [];

    await expect(fetchCompareData({
      dataSourceId: 7,
      config: {
        compare: true,
        dataSourceParams: [{
          name: 'range',
          alias_name: 'range',
          type: 'timeRange',
          value: [
            Date.parse('2026-08-14T00:00:00.000Z'),
            Date.parse('2026-08-14T01:00:00.000Z'),
          ],
        }],
      },
      getSourceDataByApiId: async (_id, params) => {
        if (!valid) throw new RuntimeRequestCancelledError();
        startedParams.push(params);
        valid = false;
        return { data: [{ value: 1 }], warnings: undefined };
      },
    })).rejects.toBeInstanceOf(RuntimeRequestCancelledError);

    expect(startedParams).toHaveLength(1);
  });
});
