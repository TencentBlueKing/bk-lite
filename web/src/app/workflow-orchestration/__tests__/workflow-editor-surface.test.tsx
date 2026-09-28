import './test-mocks';

import { App } from 'antd';
import { ReactFlowProvider } from '@xyflow/react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { WorkflowCanvasActionRail, WorkflowCanvasControls, WorkflowNodeInspector, WorkflowNodePickerPanel } from '../components/workflow-editor-surface';

describe('n8n 风格流程画布表现层', () => {
  it('使用 n8n 风格画布控件，MVP 仅保留已实现的快捷操作', () => {
    render(
      <App>
        <ReactFlowProvider>
          <WorkflowCanvasActionRail readOnly={false} onOpenPicker={vi.fn()} />
          <WorkflowCanvasControls onTidy={vi.fn()} />
        </ReactFlowProvider>
      </App>,
    );

    expect(screen.getByRole('button', { name: '添加节点' }).className).toContain('h-9!');
    expect(screen.queryByRole('button', { name: '搜索节点' })).toBeNull();
    expect(screen.getByRole('button', { name: '适应画布' }).querySelector('[data-icon="fit-canvas"]')).not.toBeNull();
    expect(screen.getByRole('button', { name: '放大' }).querySelector('.anticon-zoom-in')).not.toBeNull();
    expect(screen.getByRole('button', { name: '缩小' }).querySelector('.anticon-zoom-out')).not.toBeNull();
    expect(screen.getByRole('button', { name: '整理画布' }).querySelector('[data-icon="tidy-canvas"]')).not.toBeNull();
  });

  it('在画布内展示节点分类并支持搜索后添加', () => {
    const onPick = vi.fn();
    const onQueryChange = vi.fn();

    render(
      <App>
        <WorkflowNodePickerPanel
          open
          query="巡检"
          groups={[
            {
              key: 'action',
              title: '动作',
              description: '执行一个平台能力',
              items: [{ key: 'health-check', title: '主机巡检', description: '检查主机健康状态', onClick: onPick }],
            },
          ]}
          onQueryChange={onQueryChange}
          onClose={vi.fn()}
        />
      </App>,
    );

    expect(screen.getByRole('dialog', { name: /下一步做什么/ }).className).toContain('customDrawer');
    expect(document.querySelector('.ant-drawer-mask')).not.toBeNull();
    expect(screen.getByText('下一步做什么？')).not.toBeNull();
    fireEvent.change(screen.getByPlaceholderText('搜索节点…'), { target: { value: '报告' } });
    expect(onQueryChange).toHaveBeenCalledWith('报告');
    fireEvent.click(screen.getByRole('button', { name: /主机巡检/ }));
    expect(onPick).toHaveBeenCalledTimes(1);
  });

  it('默认以左输入、中间配置、右输出三栏展示节点数据', () => {
    const onClose = vi.fn();
    const onExecute = vi.fn();
    render(
      <App>
        <WorkflowNodeInspector
          open
          title="生成巡检报告"
          meta="bklite_report@1.0.0"
          references={[{ key: 'scan-output', label: '主机扫描 / 输出', value: '${scan.output}', type: 'object', source: '主机扫描', path: 'metrics', preview: { cpu: 42 } }]}
          outputSchema={{ type: 'object', properties: { report_url: { type: 'string' } } }}
          readOnly={false}
          onExecute={onExecute}
          onClose={onClose}
        >
          <label htmlFor="report-name">报告名称</label>
          <input id="report-name" />
        </WorkflowNodeInspector>
      </App>,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).not.toBeNull();
    expect(dialog.closest('.ant-modal')?.getAttribute('style')).toContain('1600px');
    expect(dialog.closest('.ant-modal')?.getAttribute('style')).toContain('100vw - 32px');
    expect(screen.getByRole('region', { name: '节点参数' })).not.toBeNull();
    expect(screen.getByRole('region', { name: '节点输入' })).not.toBeNull();
    expect(screen.getByRole('region', { name: '节点输出' })).not.toBeNull();
    expect(screen.queryByText('Table')).toBeNull();
    expect(screen.getByPlaceholderText('搜索上游字段')).not.toBeNull();
    expect(screen.getByText('${scan.output}')).not.toBeNull();
    const reference = screen.getByRole('button', { name: /拖拽字段/ });
    const setData = vi.fn();
    fireEvent.dragStart(reference, { dataTransfer: { effectAllowed: 'none', setData } });
    expect(setData).toHaveBeenCalledWith('application/x-bklite-workflow-reference', '${scan.output}');
    fireEvent.click(screen.getAllByText('JSON')[0]);
    expect(screen.getByText(/"主机扫描"/)).not.toBeNull();
    expect(screen.getByText(/"cpu": 42/)).not.toBeNull();
    fireEvent.click(screen.getAllByText('Schema')[1]);
    expect(screen.getByText(/report_url/)).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /执行节点/ }));
    expect(onExecute).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: /高级信息/ })).toBeNull();
    expect(screen.getByLabelText('报告名称')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '删除节点' })).toBeNull();
    expect(screen.queryByText(/修改会立即保存在当前页面/)).toBeNull();
    expect(screen.queryByRole('button', { name: /保\s*存/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /完\s*成/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('节点没有可编辑字段时不展示无效的保存操作', () => {
    render(
      <App>
        <WorkflowNodeInspector
          open
          title="汇聚"
          meta="JOIN"
          references={[]}
          outputSchema={{ type: 'object' }}
          readOnly={false}
          onClose={vi.fn()}
        >
          <div>该节点没有业务参数</div>
        </WorkflowNodeInspector>
      </App>,
    );

    expect(screen.queryByRole('button', { name: /保\s*存/ })).toBeNull();
    expect(screen.queryByText(/修改会立即保存在当前页面/)).toBeNull();
  });
});
