import React, { createRef } from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModalRef } from '@/app/monitor/types';
import MetricModal from '../metricModal';

const apiMocks = vi.hoisted(() => ({
  getMetricsGroup: vi.fn()
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ post: vi.fn(), put: vi.fn() })
}));

vi.mock('@/app/monitor/api', () => ({
  default: () => apiMocks
}));

vi.mock('@/app/monitor/context/common', () => ({
  useCommon: () => ({ groupedUnitList: [] })
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'monitor.integrations.formula': '公式',
        'monitor.integrations.dimension': '维度'
      };
      return translations[key] || key;
    }
  })
}));

vi.mock('@/components/operate-modal', () => ({
  default: ({
    visible,
    children
  }: React.PropsWithChildren<{ visible: boolean }>) =>
    visible ? <div>{children}</div> : null
}));

beforeEach(() => {
  apiMocks.getMetricsGroup.mockResolvedValue({ items: [] });
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const modes = ['add', 'edit', 'view'] as const;

describe('指标弹窗字段顺序', () => {
  it.each(modes)('%s 模式下维度紧跟在公式之后', async (type) => {
    const ref = createRef<ModalRef>();
    const { container } = render(
      <MetricModal
        ref={ref}
        onSuccess={vi.fn()}
        groupList={[]}
        monitorObject={1}
        pluginId={2}
      />
    );

    act(() => {
      ref.current?.showModal({
        type,
        title: type,
        form: {
          name: 'cpu_usage',
          display_name: 'CPU 使用率',
          query: 'avg(cpu_usage)',
          dimensions: [{ name: 'host' }],
          data_type: 'Number',
          unit: '%'
        }
      });
    });

    await waitFor(() => {
      const selector =
        type === 'view'
          ? '.ant-descriptions-item-label'
          : '.ant-form-item-label label';
      const labels = Array.from(container.querySelectorAll(selector)).map(
        (element) => element.textContent?.trim()
      );
      const formulaIndex = labels.indexOf('公式');

      expect(formulaIndex).toBeGreaterThanOrEqual(0);
      expect(labels[formulaIndex + 1]).toBe('维度');
    });
  });
});
