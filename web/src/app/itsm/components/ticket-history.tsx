'use client';

import { useState } from 'react';
import { Button, Input, Popconfirm, Radio, Tag, Timeline } from 'antd';
import { ItsmModal } from './interaction-surfaces';
import { LoadingOutlined, UserOutlined } from '@ant-design/icons';
import { NODE_PALETTE, runningNodeLabel } from '../constants/node-catalog';
import type { AutoExecutionReview, TicketHistoryItem, TicketProgressNode } from '../types';
import { NodeGlyph } from './node-glyph';
import { formatTicketTime } from './ticket-collaboration';

interface TicketHistoryProps {
  items: TicketHistoryItem[];
  nodes: TicketProgressNode[];
  retry?: (id: number) => Promise<void>;
  reconcile?: (id: number, review: AutoExecutionReview) => Promise<void>;
  busy?: boolean;
}

function ExecutionReview({ item, onClose, onSubmit }: {
  item: TicketHistoryItem; onClose: () => void; onSubmit: NonNullable<TicketHistoryProps['reconcile']>;
}) {
  const [outcome, setOutcome] = useState<AutoExecutionReview['outcome']>();
  const [note, setNote] = useState('');
  const [rawValue, setRawValue] = useState('');
  const needsResult = outcome === 'executed' && !!item.result_field;
  const submit = async () => {
    if (!item.execution_id || !item.review_token || !outcome || !note.trim()) return;
    const review: AutoExecutionReview = { review_token: item.review_token, outcome, note: note.trim() };
    if (needsResult) {
      try { review.result_value = JSON.parse(rawValue); }
      catch { throw new Error('返回值须为有效 JSON，文本请使用双引号。'); }
    }
    await onSubmit(item.execution_id, review);
    onClose();
  };
  return <ItsmModal open title={`核对「${item.name}」`} onCancel={onClose} onOk={submit} okText="确认核对"
    formValue={{ outcome, note, rawValue }} okButtonProps={{ disabled: !outcome || !note.trim() || (needsResult && !rawValue.trim()) }}>
    <div className="flex flex-col gap-3">
      <div>请根据下游系统记录核对作业 {item.job_id} 的执行结果。</div>
      <Radio.Group value={outcome} onChange={event => setOutcome(event.target.value)}>
        <Radio value="executed">已执行成功，仅推进流程</Radio>
        <Radio value="not_executed">确认未执行，重新执行动作</Radio>
      </Radio.Group>
      <label>核对依据<Input.TextArea aria-label="核对依据" placeholder="例如下游流水号、日志时间及核对结果" maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
      {needsResult && <label>返回值（回填到 {item.result_field}）<Input.TextArea aria-label="已核实的返回值" placeholder='输入返回值的 JSON，例如 "REQ-42" 或 42' value={rawValue} onChange={e => setRawValue(e.target.value)} /></label>}
    </div>
  </ItsmModal>;
}

export function TicketHistory({ items, nodes, retry, reconcile, busy }: TicketHistoryProps) {
  const [review, setReview] = useState<TicketHistoryItem>();
  const nodeTypes = new Map(nodes.map((node) => [node.id, node.type === 'handle' ? 'manual' : node.type]));
  return <><Timeline className="!pl-2 !pt-3" items={items.map((item) => {
    const type = nodeTypes.get(item.node_id) || 'unknown';
    const label = NODE_PALETTE.find((node) => node.type === type)?.label || '流程操作';
    const executionId = item.execution_id;
    const note = item.action === 'auto' ? item.message : item.action === 'auto_reconcile' ? [item.message, item.opinion].filter(Boolean).join(' · ') : item.opinion;
    return {
      key: item.id,
      dot: <span aria-label={label} className="inline-flex rounded-lg bg-[var(--color-bg)]"><NodeGlyph type={type} compact /></span>,
      children: <div className="ml-2 flex flex-col gap-1 pb-2">
        {(item.started_at || item.finished_at) && <span className="text-xs text-[var(--color-text-3)]">{formatTicketTime(item.finished_at || item.started_at)}</span>}
        <span className="text-sm font-medium text-[var(--color-text-1)]">{item.name}</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {(item.operator || !item.executing) && <Tag icon={<UserOutlined />}>{item.operator || '未分配'}</Tag>}
          {item.state === 'current' ? <Tag color="processing" icon={item.executing ? <LoadingOutlined /> : undefined}>{item.executing ? runningNodeLabel(type) : item.action === 'auto' ? item.action_label : '待处理'}</Tag> : null}
          {item.state === 'failed' ? <Tag color={item.action_label === '待核对' ? 'warning' : 'error'}>{item.action_label === '待核对' ? '待核对' : '执行失败'}</Tag> : null}
          {item.action === 'auto_retry' || item.action === 'return' || item.action === 'auto_reconcile' ? <Tag>{item.action_label}</Tag> : null}
        </div>
        {note ? <span className="whitespace-pre-wrap break-words text-xs text-[var(--color-text-2)]">{note}</span> : null}
        {item.job_records?.map(record => <a key={record.job_id} className="self-start text-xs" target="_blank" rel="noopener noreferrer"
          href={`/job/execution/job-record?id=${record.job_id}`}>
          第 {record.row} 行 · 作业 #{record.job_id}
        </a>)}
        {item.review_token && executionId && reconcile && <Button size="small" className="self-start" disabled={busy} onClick={() => setReview(item)}>核对执行结果</Button>}
        {item.can_retry && executionId && retry ? (
          <Popconfirm title={`重试「${item.name}」？`} description="系统会根据执行记录恢复此节点。" okText="确认重试" onConfirm={() => retry(executionId)}>
            <Button size="small" className="self-start" disabled={busy}>重试节点</Button>
          </Popconfirm>
        ) : null}
      </div>,
    };
  })} />{review && reconcile && <ExecutionReview item={review} onClose={() => setReview(undefined)} onSubmit={reconcile} />}</>;
}
