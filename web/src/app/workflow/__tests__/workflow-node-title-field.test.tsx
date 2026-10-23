import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { WorkflowNodeTitleField } from '../components/workflow-node-title-field';
import { WORKFLOW_REFERENCE_MIME } from '../components/workflow-template-text-field';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

describe('节点名称字段', () => {
  it('拖入上游引用时提示且不改内容', async () => {
    const onChange = vi.fn();
    render(
      <App>
        <WorkflowNodeTitleField value="HTTP 请求" onChange={onChange} />
      </App>,
    );

    fireEvent.drop(screen.getByTestId('workflow-reference-drop-guard'), {
      dataTransfer: {
        dropEffect: 'copy',
        types: [WORKFLOW_REFERENCE_MIME],
        getData: vi.fn().mockReturnValue('${system.execution_id}'),
      },
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('HTTP 请求')).not.toBeNull();
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/节点名称只用于画布展示/);
    });
  });
});
