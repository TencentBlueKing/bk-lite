import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const navigation = vi.hoisted(() => ({
  replace: vi.fn(),
  query: 'model_id=host&inst_uuid=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa&inst_name=web-1',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: navigation.replace }),
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

import RelatedTopologyLegacyRedirect from '../page';

afterEach(() => {
  cleanup();
  navigation.replace.mockReset();
  navigation.query =
    'model_id=host&inst_uuid=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa&inst_name=web-1';
});

describe('relatedTopology legacy redirect', () => {
  it('replaces to relationships with the original query and tab=topo', async () => {
    render(<RelatedTopologyLegacyRedirect />);
    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledTimes(1);
    });
    const href = String(navigation.replace.mock.calls[0]?.[0]);
    const url = new URL(href, 'https://example.test');
    expect(url.pathname).toBe('/cmdb/assetData/detail/relationships');
    expect(url.searchParams.get('model_id')).toBe('host');
    expect(url.searchParams.get('inst_uuid')).toBe(
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    );
    expect(url.searchParams.get('inst_name')).toBe('web-1');
    expect(url.searchParams.get('tab')).toBe('topo');
  });

  it('overwrites an existing tab so the topo slot is selected', async () => {
    navigation.query = 'model_id=host&tab=list';
    render(<RelatedTopologyLegacyRedirect />);
    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledTimes(1);
    });
    const href = String(navigation.replace.mock.calls[0]?.[0]);
    const url = new URL(href, 'https://example.test');
    expect(url.searchParams.get('tab')).toBe('topo');
    expect(url.searchParams.get('model_id')).toBe('host');
  });
});
