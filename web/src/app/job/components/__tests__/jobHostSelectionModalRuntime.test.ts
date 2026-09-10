import { describe, expect, it } from 'vitest';

import {
  formatHostSelectionLabel,
  resolveHostPaginationChange,
} from '../host-selection-modal';
import {
  buildNodeQueryParams,
  buildTargetQueryParams,
} from '../jobHostSelectionModalRuntime';

const filters = {
  keyword: [{ lookup_expr: 'icontains', value: '10.93.160.2' }],
  os_type: [{ lookup_expr: 'in', value: ['linux'] }],
};

const signal = new AbortController().signal;

describe('buildNodeQueryParams', () => {
  it('maps the host-name filter for node-manager hosts', () => {
    expect(buildNodeQueryParams({
      page: 1,
      pageSize: 20,
      filters: {
        keyword: [{ lookup_expr: 'icontains', value: 'OneDC_UICamA01' }],
      },
      source: 'node_manager',
      signal,
    })).toEqual({
      page: 1,
      page_size: 20,
      keyword: 'OneDC_UICamA01',
      os: undefined,
    });
  });

  it('maps fuzzy search and operating-system filters for node-manager hosts', () => {
    expect(buildNodeQueryParams({
      page: 1,
      pageSize: 20,
      filters,
      source: 'node_manager',
      signal,
    })).toEqual({
      page: 1,
      page_size: 20,
      keyword: '10.93.160.2',
      os: 'linux',
    });
  });

  it('maps fuzzy search and operating-system filters for target-manager hosts', () => {
    expect(buildTargetQueryParams({
      page: 2,
      pageSize: 50,
      filters,
      source: 'target_manager',
      signal,
    })).toEqual({
      page: 2,
      page_size: 50,
      search: '10.93.160.2',
      os_type: 'linux',
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

describe('formatHostSelectionLabel', () => {
  it('shows the target name followed by its IP address', () => {
    expect(formatHostSelectionLabel({
      key: 'host-1',
      hostName: 'beijing-ai-01',
      ipAddress: '10.0.1.41',
      cloudRegion: 'default',
      osType: 'Linux',
      currentDriver: 'SSH',
    }, 'host-1')).toBe('beijing-ai-01 (10.0.1.41)');
  });
});
