import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
const replace = vi.fn();
let search = 'screen=true';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push,
    replace,
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(search),
}));

import { useScreenAwareRouter } from '../useScreenAwareRouter';

describe('useScreenAwareRouter', () => {
  beforeEach(() => {
    push.mockClear();
    replace.mockClear();
  });

  it('adds screen to push and replace when the current query is screen mode', () => {
    search = 'screen=true';
    const { result } = renderHook(() => useScreenAwareRouter());

    result.current.push('/monitor/view?objId=4');
    result.current.replace('/cmdb/assetData?modelId=host', { scroll: false });

    expect(push).toHaveBeenCalledWith('/monitor/view?objId=4&screen=true');
    expect(replace).toHaveBeenCalledWith(
      '/cmdb/assetData?modelId=host&screen=true',
      { scroll: false },
    );
  });

  it('does not add screen when the current query is ordinary', () => {
    search = '';
    const { result } = renderHook(() => useScreenAwareRouter());

    result.current.push('/monitor/view?objId=4');

    expect(push).toHaveBeenCalledWith('/monitor/view?objId=4');
  });
});
