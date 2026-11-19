'use client';
import { Alert, Button, Empty, Form, Tag, Tooltip, message } from 'antd';
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { FormRenderer } from './form-renderer';
import { NodeGlyph } from './node-glyph';
import { NODE_ACTIONS, NODE_PALETTE } from '../constants/node-catalog';
import type { FlowDesign } from '../constants/demo-flow';
import type { FormSchema } from '../types';

export function WorkflowPreview({ schema, design }: { schema: FormSchema; design: FlowDesign }) {
  const [selected, setSelected] = useState(design.nodes.find(node=>node.type==='submit')?.id || design.nodes[0]?.id);
  const [form] = Form.useForm();
  const [revision, setRevision] = useState(0);
  const node = design.nodes.find(item=>item.id===selected) || design.nodes[0];
  const nodeName = (item: FlowDesign['nodes'][number]) => item.name || NODE_PALETTE.find(entry=>entry.type===item.type)?.label || item.id;
  const interactive = node && ['submit','approval','manual','handle','manual_trigger','subprocess_handle'].includes(node.type);
  const requiredOpinions = node?.required_opinion_actions ?? [];
  const defaultActions = NODE_PALETTE.find(item => item.type === node?.type)?.actions ?? [];
  const actions = node?.actions ?? Array.from(new Set([...defaultActions, ...requiredOpinions]));
  const requiredLabels = NODE_ACTIONS.filter(option => actions.includes(option.value) && requiredOpinions.includes(option.value)).map(option => option.label);
  return <section aria-label="流程预览" className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
      <div><span className="text-sm font-medium">节点预览</span><p className="mt-1 text-xs text-[var(--color-text-3)]">仅预览配置，不会创建工单或执行流程。</p></div>
      <div className="flex gap-2"><Tooltip title="重置预览数据"><Button aria-label="重置预览数据" icon={<ReloadOutlined />} onClick={()=>{form.resetFields();setRevision(value=>value+1);}} /></Tooltip>
      <Button icon={<CheckCircleOutlined />} disabled={!interactive} onClick={()=>void form.validateFields().then(()=>message.success('当前节点表单校验通过')).catch(()=>message.warning('请检查表单中标红的字段'))}>校验表单</Button></div>
    </div>
    <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto md:grid-cols-[220px_minmax(0,1fr)] md:overflow-hidden">
      <nav aria-label="预览节点" className="flex gap-2 overflow-auto border-b border-[var(--color-border)] p-3 md:flex-col md:border-b-0 md:border-r">
        {design.nodes.map(item=><button key={item.id} type="button" aria-label={`预览${nodeName(item)}`} aria-current={item.id===node?.id?'step':undefined} onClick={()=>setSelected(item.id)} className={`flex shrink-0 items-center gap-2 rounded-lg border p-3 text-left text-sm transition-colors ${item.id===node?.id?'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]':'border-transparent hover:bg-[var(--color-fill-1)]'}`}><NodeGlyph type={item.type} compact /><span className="truncate">{nodeName(item)}</span></button>)}
      </nav>
      <div className="min-h-0 overflow-auto bg-[var(--color-fill-1)] p-4 md:p-6">
        <div className="min-h-full w-full min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-5">
          <div className="mb-5 border-b border-[var(--color-border)] pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">{node && <NodeGlyph type={node.type} compact />}<span className="text-sm font-semibold">{node ? nodeName(node) : '尚未配置节点'}</span><Tag>{NODE_PALETTE.find(item=>item.type===node?.type)?.label || '节点'}</Tag></div>
              <div aria-label="节点操作预览" className="flex flex-wrap gap-1">{actions.map(action=><Tag key={action}>{NODE_ACTIONS.find(item=>item.value===action)?.label || action}</Tag>)}</div>
            </div>
            {requiredLabels.length > 0 && <p className="mt-2 text-right text-xs text-[var(--color-text-3)]">{requiredLabels.join('、')}前需填写处理意见。</p>}
          </div>
          {interactive ? <FormRenderer key={`${node.id}-${revision}`} form={form} schema={schema} fieldPerm={node.field_perm as Parameters<typeof FormRenderer>[0]['fieldPerm']} fetchContext={{preview:true,schema}} hideSubmit onSubmit={()=>undefined} /> : node ? <Alert type="info" showIcon message="此节点由流程引擎执行，无需填写表单。请选择提单、审批或人工处理节点查看表单。" /> : <Empty description="请先添加流程节点" />}
        </div>
      </div>
    </div>
  </section>;
}
