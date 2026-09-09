import { describe, expect, it } from 'vitest';

import { resolveHostPaginationChange } from '../host-selection-modal';
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

describe('resolveHostPaginationChange', () => {
  it('returns to the first page when the page size changes', () => {
    expect(resolveHostPaginationChange({
      currentPageSize: 20,
      nextPage: 2,
      nextPageSize: 50,
    })).toEqual({
      page: 1,
      pageSize: 50,
    });
  });

  it('keeps the requested page when the page size is unchanged', () => {
    expect(resolveHostPaginationChange({
      currentPageSize: 20,
      nextPage: 2,
      nextPageSize: 20,
    })).toEqual({
      page: 2,
      pageSize: 20,
    });
  });
});
