'use client';

import { DeleteOutlined, EditOutlined, EyeOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Handle, NodeToolbar, Position, useNodeConnections, type Node, type NodeProps } from '@xyflow/react';
import { Button, Tooltip } from 'antd';
import type { ReactNode } from 'react';

import { useTranslation } from '@/utils/i18n';
import type { WorkflowCanvasNodeData } from '../lib/canvas-dsl';
import { AtomIcon } from './atom-icon';
import { WorkflowPermission } from './workflow-permission';

export type WorkflowNodeAction = 'configure' | 'test' | 'detail' | 'delete' | 'add';
export interface InteractiveWorkflowNodeData extends WorkflowCanvasNodeData {
  readOnly?: boolean;
  locked?: boolean;
  testState?: 'idle' | 'running' | 'started';
  onAction?: (action: WorkflowNodeAction, reference: string, sourceHandle?: string) => void;
}
type WorkflowNode = Node<InteractiveWorkflowNodeData, 'workflowCanvas'>;

function NodeIcon({ data }: { data: InteractiveWorkflowNodeData }) {
  if (data.kind === 'trigger') return <AtomIcon nodeType="TRIGGER" className="text-5xl" />;
  if (data.kind === 'return') return <AtomIcon nodeType="RETURN" className="text-5xl" />;
  if (data.kind === 'control') {
    if (data.taskType === 'HUMAN') return <AtomIcon nodeType="CONTROL" controlKind="approval" className="text-5xl" />;
    if (data.taskType === 'SWITCH') return <AtomIcon nodeType="CONTROL" controlKind="condition" className="text-5xl" />;
    return <AtomIcon nodeType="CONTROL" className="text-5xl" />;
  }
  return <AtomIcon nodeType="ACTION" category={data.atomCategory} className="text-5xl" />;
}

function ToolbarButton({ label, icon, danger, operation, onClick }: { label: string; icon: ReactNode; danger?: boolean; operation: 'View' | 'Edit' | 'Execute'; onClick: () => void }) {
  return <WorkflowPermission operation={operation}><Tooltip title={label}><Button className={`h-7! w-7! min-w-7! rounded-sm! p-0! text-xs! text-[var(--color-text-1)]! hover:bg-[var(--color-bg-hover)]! ${danger ? 'hover:text-[var(--color-fail)]!' : ''}`} aria-label={label} type="text" size="small" icon={icon} onClick={(event) => { event.stopPropagation(); onClick(); }} /></Tooltip></WorkflowPermission>;
}

function HandleExtension({ top, label, onClick }: { top: string; label?: string; onClick: () => void }) {
  const { t } = useTranslation();
  return <div className="pointer-events-none absolute left-[104px] z-10 h-6 w-[90px] -translate-y-1/2" style={{ top: `calc(${top} - 1px)` }}>
    <span className="absolute left-0 top-1/2 w-[68px] border-t-2 border-[var(--color-border-3)]" />
    {label ? <span className="absolute left-1 top-[calc(50%+1px)] -translate-y-1/2 bg-[var(--color-fill-1)]/85 text-xs leading-3 text-[var(--color-text-3)]">{label}</span> : null}
    <WorkflowPermission operation="Edit"><button
      type="button"
      aria-label={label ? t('workflowOrchestration.editor.addFromBranch', '从 {label} 分支添加节点', { label }) : t('workflowOrchestration.editor.addNext', '从此节点添加下一步')}
      className="nodrag nopan pointer-events-auto absolute left-[68px] top-1/2 grid h-5 w-5 -translate-y-1/2 place-items-center rounded bg-[var(--color-fill-2)] text-sm font-medium leading-none text-[var(--color-text-2)] shadow-sm hover:bg-[var(--color-fill-3)]"
      onClick={(event) => { event.stopPropagation(); onClick(); }}
    >+</button></WorkflowPermission>
  </div>;
}

export function WorkflowCanvasNode({ id, data, selected }: NodeProps<WorkflowNode>) {
  const { t } = useTranslation();
  const defaultSourceConnections = useNodeConnections({ handleType: 'source' });
  const act = (action: WorkflowNodeAction, sourceHandle?: string) => data.onAction?.(action, id, sourceHandle);
  const executableNode = (data.kind === 'atom' || data.kind === 'trigger') && !data.readOnly && !data.locked;
  const handleClassName = 'h-4! w-4! border! border-[var(--color-border-4)]! bg-[var(--color-bg)]!';
  const cardShape = data.kind === 'trigger' ? 'rounded-[36px_8px_8px_36px]' : 'rounded-lg';
  const branches = (data.branches?.length
    ? data.branches
    : data.taskType === 'SWITCH'
      ? [{ id: 'true', label: '满足' }, { id: 'false', label: '不满足' }]
      : data.taskType === 'HUMAN'
        ? [{ id: 'true', label: '通过' }, { id: 'false', label: '驳回' }]
        : []
  ).map((branch) => {
    // 条件是布尔 SWITCH（满足/不满足）；审批才是通过/驳回。不要仅凭 true/false id 套用审批文案。
    const label = branch.label === '通过'
      ? t('workflowOrchestration.editor.approvalBranchPass', '通过')
      : branch.label === '驳回'
        ? t('workflowOrchestration.editor.approvalBranchReject', '驳回')
        : branch.label === '超时' || branch.id === 'timeout'
          ? t('workflowOrchestration.editor.approvalBranchTimeout', '超时')
          : branch.label === '满足' || (data.taskType === 'SWITCH' && branch.id === 'true')
            ? t('workflowOrchestration.editor.conditionBranchMatch', '满足')
            : branch.label === '不满足' || (data.taskType === 'SWITCH' && branch.id === 'false')
              ? t('workflowOrchestration.editor.conditionBranchMiss', '不满足')
              : data.taskType === 'HUMAN' && branch.id === 'true'
                ? t('workflowOrchestration.editor.approvalBranchPass', '通过')
                : data.taskType === 'HUMAN' && branch.id === 'false'
                  ? t('workflowOrchestration.editor.approvalBranchReject', '驳回')
                  : branch.label;
    return { ...branch, label };
  });
  return <div className="relative h-24 w-24 text-center" data-workflow-node={data.kind}>
    {data.kind !== 'trigger' && <Handle type="target" position={Position.Left} className={handleClassName} />}
    <NodeToolbar isVisible={selected} position={Position.Top} offset={12}>
      <div className="flex h-7 items-center overflow-hidden rounded bg-[var(--color-fill-2)]">
        {executableNode && <ToolbarButton label={t('workflowOrchestration.editor.singleStep', '单步执行')} operation="Execute" icon={<PlayCircleOutlined />} onClick={() => act('test')} />}
        <ToolbarButton label={data.readOnly ? t('common.view', '查看') : t('workflowOrchestration.editor.configure', '配置')} operation={data.readOnly ? 'View' : 'Edit'} icon={<EditOutlined />} onClick={() => act('configure')} />
        {data.kind === 'atom' && <ToolbarButton label={t('workflowOrchestration.editor.viewAtomDetails', '查看原子详情')} operation="View" icon={<EyeOutlined />} onClick={() => act('detail')} />}
        {!data.readOnly && !data.locked && <ToolbarButton label={t('workflowOrchestration.editor.deleteNode', '删除节点')} operation="Edit" danger icon={<DeleteOutlined />} onClick={() => act('delete')} />}
      </div>
    </NodeToolbar>
    <WorkflowPermission operation="View" className="block"><button
      type="button"
      aria-label={data.title}
      title={data.meta}
      className={`grid h-24 w-24 place-items-center bg-[var(--color-bg)] text-[var(--color-text-2)] transition-shadow duration-150 ${cardShape} ${selected ? 'border border-[var(--color-border-2)] shadow-[0_0_0_6px_color-mix(in_srgb,var(--color-text-2)_10%,transparent)]' : 'border-[1.5px] border-[var(--color-border-2)] hover:shadow-[0_0_0_6px_var(--color-bg-hover)]'}`}
      onDoubleClick={() => act('configure')}
    >
      {data.testState === 'running' ? <ReloadOutlined spin /> : <NodeIcon data={data} />}
    </button></WorkflowPermission>
    <div className="pointer-events-none absolute left-1/2 top-[102px] w-48 -translate-x-1/2 text-base font-medium leading-5 text-[var(--color-text-1)]" title={data.title}>{data.title}</div>
    {data.testState === 'started' && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full border-2 border-[var(--color-bg)] bg-[var(--color-success)]" title={t('workflowOrchestration.editor.singleStepStarted', '单步执行已启动')} />}
    {branches.length ? <>{branches.map((branch, index) => {
      const top = `${((index + 1) / (branches.length + 1)) * 100}%`;
      const connected = defaultSourceConnections.some((connection) => connection.sourceHandle === branch.id);
      return <div key={branch.id}>
        <Handle id={branch.id} type="source" position={Position.Right} className={handleClassName} style={{ top }} />
        {!connected && !data.readOnly && !data.locked
          ? <HandleExtension top={top} label={branch.label} onClick={() => act('add', branch.id)} />
          : <span className="pointer-events-none absolute left-[108px] z-10 -translate-y-1/2 bg-[var(--color-fill-1)]/85 text-xs leading-3 text-[var(--color-text-3)]" style={{ top }}>{branch.label}</span>}
      </div>;
    })}</> : data.kind !== 'return' && <>
      <Handle type="source" position={Position.Right} className={handleClassName} />
      {!defaultSourceConnections.length && !data.readOnly && !data.locked ? <HandleExtension top="50%" onClick={() => act('add')} /> : null}
    </>}
  </div>;
}
