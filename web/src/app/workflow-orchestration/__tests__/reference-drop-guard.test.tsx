import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { ReferenceDropGuard } from '../components/reference-drop-guard';
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

describe('引用拖拽护栏', () => {
  it('点选字段拖入上游引用时提示且不改内容', async () => {
    render(
      <App>
        <ReferenceDropGuard>
          <input aria-label="channel" defaultValue="keep" />
        </ReferenceDropGuard>
      </App>,
    );

    const dataTransfer = {
      dropEffect: 'copy',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn().mockReturnValue('${workflow.input.triggered_at}'),
    };
    fireEvent.drop(screen.getByTestId('workflow-reference-drop-guard'), { dataTransfer });
    expect((screen.getByLabelText('channel') as HTMLInputElement).value).toBe('keep');
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/不支持拖入上游字段/);
    });
  });
});
