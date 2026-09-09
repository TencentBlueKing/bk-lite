import { describe, expect, it } from 'vitest';

import { buildNodeQueryParams } from '../jobHostSelectionModalRuntime';

describe('buildNodeQueryParams', () => {
  it('uses the shared fuzzy keyword when searching node-manager hosts by IP', () => {
    expect(buildNodeQueryParams({
      page: 1,
      pageSize: 20,
      search: '10.93.160.2',
      source: 'node_manager',
    })).toEqual({
      page: 1,
      page_size: 20,
      keyword: '10.93.160.2',
    });
  });
});
