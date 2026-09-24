import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeAll, beforeEach, vi } from 'vitest';

import { WorkflowTriggerRuntimeForm } from '../components/workflow-trigger-runtime-form';
import type { JsonSchema } from '../lib/types';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, post: mocks.post }),
}));

const schema: JsonSchema = {
  type: 'object',
  properties: {
    targets: {
      type: 'array',
      title: '目标主机',
      items: { type: 'string' },
      minItems: 1,
      maxItems: 10,
      'x-widget': 'target-selector',
      'x-target-binding': {
        mode: 'runtime',
        allowedSources: ['node_mgmt', 'job_mgmt'],
        allowedOperatingSystems: ['linux', 'windows'],
        minCount: 1,
        maxCount: 10,
      },
    },
    report_template: {
      type: 'object',
      title: '报告模板',
      'x-widget': 'file-upload',
      'x-file-options': {
        accept: ['docx', 'xlsx'], maxSizeMiB: 5, maxCount: 1, sourceModes: ['upload'],
        sampleFiles: [
          { name: 'Word', url: '/workflow-orchestration/templates/health-inspection-example.docx' },
          { name: 'Excel', url: '/workflow-orchestration/templates/health-inspection-example.xlsx' },
        ],
      },
    },
  },
  required: ['targets', 'report_template'],
};

function Harness() {
  const [value, setValue] = useState<Record<string, unknown>>({ targets: [] });
  return <App><WorkflowTriggerRuntimeForm workflowId={9} schema={schema} value={value} onChange={setValue} /></App>;
}

describe('表单触发运行表单', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.get.mockResolvedValue({ source: 'node_mgmt', count: 1, items: [{ id: 'node:1', source: 'node_mgmt', source_id: '1', name: 'host-01', ip: '10.0.0.1', operating_system: 'linux' }] });
  });

  it('按表单 Schema 渲染主机选择器和文件上传', async () => {
    render(<Harness />);

    expect(screen.getByText('目标主机')).not.toBeNull();
    expect(screen.getByText('报告模板')).not.toBeNull();
    expect(screen.getByRole('button', { name: /选择 Word \/ Excel 模板/ })).not.toBeNull();
    expect(screen.queryByText('请上传一份报告模板后再启动')).toBeNull();
    expect(screen.getByRole('link', { name: 'Word' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.docx');
    expect(screen.getByRole('link', { name: 'Excel' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.xlsx');

    fireEvent.click(screen.getByRole('button', { name: /请选择目标主机/ }));

    expect(await screen.findByRole('dialog', { name: /选择主机 · 目标主机/ })).not.toBeNull();
    await waitFor(() => expect(screen.getByText('host-01')).not.toBeNull());
    expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('/workflows/targets/?source=node_mgmt'), expect.anything());
  });
});
