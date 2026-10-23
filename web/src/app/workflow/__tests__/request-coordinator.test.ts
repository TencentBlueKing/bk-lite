import { describe, expect, it, vi } from 'vitest';

import { createRequestCoordinator } from '../lib/request-coordinator';

describe('编排中心请求协调器', () => {
  it('高频切换时取消旧请求且只允许最新响应更新页面', () => {
    const onLoadingChange = vi.fn();
    const coordinator = createRequestCoordinator(onLoadingChange);
    const first = coordinator.begin({ visible: true });
    const second = coordinator.begin({ visible: true });

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(first?.signal.aborted).toBe(true);
    expect(coordinator.shouldApply(first!)).toBe(false);
    expect(coordinator.shouldApply(second!)).toBe(true);

    coordinator.finish(first!);
    expect(onLoadingChange).not.toHaveBeenLastCalledWith(false);
    coordinator.finish(second!);
    expect(onLoadingChange).toHaveBeenLastCalledWith(false);
  });
});
