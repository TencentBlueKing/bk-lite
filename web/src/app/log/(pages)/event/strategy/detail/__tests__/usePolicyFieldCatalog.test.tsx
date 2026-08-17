import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import usePolicyFieldCatalog from '../usePolicyFieldCatalog';

const getFields = vi.fn();

vi.mock('@/app/log/api/integration', () => ({
  default: () => ({ getFields })
}));

describe('usePolicyFieldCatalog', () => {
  beforeEach(() => {
    getFields.mockReset();
  });

  it('空日志分组不请求字段目录', () => {
    const { result } = renderHook(() => usePolicyFieldCatalog([]));

    expect(getFields).not.toHaveBeenCalled();
    expect(result.current).toEqual({ fields: [], loading: false });
  });

  it('按已选日志分组加载字段目录', async () => {
    getFields.mockResolvedValue(['level', 'host.name']);
    const { result } = renderHook(() =>
      usePolicyFieldCatalog(['group-b', 'group-a'])
    );

    expect(getFields).toHaveBeenCalledWith(
      expect.objectContaining({
        query: '*',
        start_time: expect.any(String),
        end_time: expect.any(String),
        log_groups: ['group-a', 'group-b']
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    const fieldParams = getFields.mock.calls[0][0];
    expect(
      new Date(fieldParams.end_time).getTime() -
        new Date(fieldParams.start_time).getTime()
    ).toBe(15 * 60 * 1000);
    await waitFor(() => {
      expect(result.current).toEqual({
        fields: ['level', 'host.name'],
        loading: false
      });
    });
  });

  it('切换日志分组后忽略旧请求结果', async () => {
    let resolveOldRequest: (fields: string[]) => void = () => undefined;
    getFields
      .mockImplementationOnce(
        () =>
          new Promise<string[]>((resolve) => {
            resolveOldRequest = resolve;
          })
      )
      .mockResolvedValueOnce(['new.field']);

    const { result, rerender } = renderHook(
      ({ groups }) => usePolicyFieldCatalog(groups),
      { initialProps: { groups: ['old-group'] } }
    );
    const oldSignal = getFields.mock.calls[0][1].signal as AbortSignal;

    rerender({ groups: ['new-group'] });
    expect(oldSignal.aborted).toBe(true);
    await waitFor(() => {
      expect(result.current.fields).toEqual(['new.field']);
    });

    await act(async () => {
      resolveOldRequest(['old.field']);
      await Promise.resolve();
    });
    expect(result.current.fields).toEqual(['new.field']);
  });
});
