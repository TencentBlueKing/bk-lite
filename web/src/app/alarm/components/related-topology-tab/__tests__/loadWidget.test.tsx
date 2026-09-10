import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useRelatedTopologyTab } from '../index';

const mocks = vi.hoisted(() => ({
  capability: {
    status: 'ready' as const,
    api: {
      RelatedTopologyWidget: vi.fn(),
    },
  },
}));

vi.mock('@/context/appCapabilities', () => ({
  useAppCapability: () => mocks.capability,
}));

const OBJECTS = [
  {
    monitor_id: 'm-1',
    cmdb_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    resource_type: 'host',
    resource_name: 'web-1',
  },
];

describe('useRelatedTopologyTab widget loader', () => {
  it('surfaces a failed chunk load instead of spinning', async () => {
    mocks.capability.api.RelatedTopologyWidget.mockRejectedValueOnce(
      new Error('missing chunk'),
    );

    const { result } = renderHook(() => useRelatedTopologyTab(OBJECTS));

    await waitFor(() => {
      expect(result.current.loadFailed).toBe(true);
    });
    expect(result.current.visible).toBe(true);
    expect(result.current.Widget).toBeNull();
  });
});
