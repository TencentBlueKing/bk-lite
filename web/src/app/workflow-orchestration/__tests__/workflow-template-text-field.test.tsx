import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import {
  computeSuggestionMenuPosition,
  matchTemplateTrigger,
  WorkflowTemplateTextField,
  WORKFLOW_REFERENCE_MIME,
} from '../components/workflow-template-text-field';

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

const references = [
  { label: '作业 · 全部输出', value: '${job_execute.output}', source: '作业', type: 'object', displayName: '全部输出' },
  { label: '运行信息 · 流程版本', value: '${system.workflow_version}', source: '运行信息', type: 'integer', displayName: '流程版本' },
];

function Harness({ rows = 4 }: { rows?: number }) {
  const [value, setValue] = useState('你好 ');
  return (
    <App>
      <WorkflowTemplateTextField value={value} references={references} rows={rows} onChange={setValue} />
    </App>
  );
}

describe('文本模板输入', () => {
  it('识别光标前的 $ 触发串', () => {
    expect(matchTemplateTrigger('你好 $', 4)).toEqual({ start: 3, query: '' });
    expect(matchTemplateTrigger('你好 ${job', 10)).toEqual({ start: 3, query: '{job' });
    expect(matchTemplateTrigger('完成了', 3)).toBeNull();
  });

  it('底部空间不足时把建议列表翻到输入框上方', () => {
    const nearBottom = {
      top: 700,
      bottom: 760,
      left: 100,
      width: 320,
      height: 60,
      right: 420,
      x: 100,
      y: 700,
      toJSON: () => ({}),
    } as DOMRect;
    const position = computeSuggestionMenuPosition(nearBottom, 800);
    expect(position.placement).toBe('top');
    expect(position.top + position.maxHeight).toBeLessThanOrEqual(nearBottom.top);
    expect(position.maxHeight).toBeGreaterThan(0);
  });

  it('滚动建议列表本身不会关闭下拉', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole('textbox');
    await user.click(input);
    await user.type(input, '$');
    const menu = screen.getByTestId('workflow-template-suggestions');
    fireEvent.scroll(menu);
    expect(screen.getByTestId('workflow-template-suggestions')).not.toBeNull();
  });

  it('输入 $ 后展示上游字段下拉，并可选中插入', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByRole('textbox');
    await user.click(input);
    await user.type(input, '$');

    expect(screen.getByTestId('workflow-template-suggestions')).not.toBeNull();
    expect(screen.getByText('${job_execute.output}')).not.toBeNull();
    expect(screen.getByText('${system.workflow_version}')).not.toBeNull();

    await user.click(screen.getByText('全部输出'));
    expect(screen.getByDisplayValue('你好 ${job_execute.output}')).not.toBeNull();
    expect(screen.queryByTestId('workflow-template-suggestions')).toBeNull();
  });

  it('拖入引用时插入到当前光标位置', () => {
    render(<Harness />);
    const dataTransfer = {
      dropEffect: 'none',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn().mockImplementation((format: string) => (
        format === WORKFLOW_REFERENCE_MIME ? '${job_execute.output}' : ''
      )),
    };
    fireEvent.drop(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });
    expect(screen.getByDisplayValue('你好 ${job_execute.output}')).not.toBeNull();
  });

  it('拖入悬停时自行高亮，无需外部 isDragOver', () => {
    render(<Harness />);
    const zone = screen.getByTestId('workflow-reference-dropzone');
    const dataTransfer = {
      dropEffect: 'none',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn().mockReturnValue(''),
    };
    fireEvent.dragEnter(zone, { dataTransfer });
    expect(zone.className).toContain('ring-[var(--color-primary)]/35');
    fireEvent.dragLeave(zone, { dataTransfer });
    expect(zone.className).not.toContain('ring-[var(--color-primary)]/35');
  });
});
