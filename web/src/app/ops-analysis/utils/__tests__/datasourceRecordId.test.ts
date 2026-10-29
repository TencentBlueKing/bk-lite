import { describe, expect, it } from 'vitest';

import {
  readDatasourceLookupList,
  retainRequestedDatasources,
} from '@/app/ops-analysis/utils/datasourceRecordId';

describe('share datasource lookup payload', () => {
  it('keeps required_app on stubs whose id arrives as text', () => {
    const retained = retainRequestedDatasources(
      readDatasourceLookupList([
        { id: '12', hasAuth: false, required_app: 'alarm' },
        { id: 13, hasAuth: true, required_app: 'monitor', rest_api: 'monitor/query' },
      ]),
      [12, 13],
    );

    expect(retained).toEqual([
      { id: 12, hasAuth: false, required_app: 'alarm' },
      { id: 13, hasAuth: true, required_app: 'monitor', rest_api: 'monitor/query' },
    ]);
    expect('rest_api' in retained[0]).toBe(false);
  });

  it('reads a wrapped items list without dropping required_app', () => {
    const retained = retainRequestedDatasources(
      readDatasourceLookupList({
        items: [{ id: 7, hasAuth: false, required_app: 'alarm' }],
      }),
      [7],
    );

    expect(retained).toEqual([{ id: 7, hasAuth: false, required_app: 'alarm' }]);
  });
});
