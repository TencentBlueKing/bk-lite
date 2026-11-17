'use client';

import ItsmListTable from '../../components/itsm-list-table';
import { ItsmListToolbar } from '../../components/list-controls';
import { Button, Input, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';
import type { WorkflowListItem } from '../../types';

interface VariableItem {
  id: number;
  key: string;
  name: string;
}

export default function WorkflowVariablesPage() {
  const api = useItsmApi();
  const [keyword,setKeyword] = useState('');
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [workflowId, setWorkflowId] = useState<number | undefined>();
  const [variables, setVariables] = useState<VariableItem[]>([]);
  const [keyName, setKeyName] = useState('');
  const [sample, setSample] = useState('');
  const [result, setResult] = useState('');

  const load = useCallback(async (id?: number) => {
    const data = await api.listWorkflows() as { items?: WorkflowListItem[] };
    const items = data.items || [];
    setWorkflows(items);
    const nextId = id || items[0]?.id;
    setWorkflowId(nextId);
    if (!nextId) {
      setVariables([]);
      return;
    }
    const variableData = await api.listVariables(nextId) as { items?: VariableItem[] };
    setVariables(variableData.items || []);
  }, [api.listVariables, api.listWorkflows]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : '加载失败'));
  }, [api.ready, load]);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
      <ItsmListToolbar search={{value:keyword,onChange:setKeyword,placeholder:'搜索变量名称或标识'}} leading={<Select aria-label="流程" className="w-60 max-w-full" showSearch optionFilterProp="label" value={workflowId} options={workflows.map(item=>({value:item.id,label:item.name}))} onChange={value=>void load(value)} />} />
      <ItsmListTable queryKey={`${workflowId}:${keyword}`} rowKey="id" dataSource={variables.filter(item=>`${item.key} ${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[{title:'标识',dataIndex:'key',key:'key'},{title:'名称',dataIndex:'name',key:'name'}]} />
      <div className="flex flex-wrap gap-2">
        <Input className="w-40" placeholder="变量 key" value={keyName} onChange={(event) => setKeyName(event.target.value)} />
        <Input className="w-64" placeholder="表单值，如 title=服务器" value={sample} onChange={(event) => setSample(event.target.value)} />
        <Button
          type="primary"
          onClick={() => {
            if (!workflowId || !keyName.trim()) {
              return;
            }
            const formData: Record<string, string> = {};
            sample.split(',').forEach((pair) => {
              const [field, value] = pair.split('=');
              if (field && value != null) {
                formData[field.trim()] = value.trim();
              }
            });
            void api.testVariable({ workflow_id: workflowId, key: keyName.trim(), form_data: formData }).then((data) => {
              const payload = data as { value?: unknown; source?: string };
              setResult(`${payload.source || ''} = ${String(payload.value ?? '')}`);
            }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '测试失败'));
          }}
        >
          测试
        </Button>
      </div>
      {result ? <div className="text-sm">{result}</div> : null}
    </div>
  );
}
