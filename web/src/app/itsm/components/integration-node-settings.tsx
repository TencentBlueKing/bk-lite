'use client';

import { useEffect, useState } from 'react';
import { Alert, Input, Select, message as antdMessage } from 'antd';
import { useItsmApi } from '../api/useItsmApi';
import type { IntegrationItem } from '../form/integrations/helpers';
import { parseInputs } from '../form/integrations/helpers';

export function IntegrationNodeSettings({ config, onChange }: { config: Record<string, unknown>; onChange: (config: Record<string, unknown>) => void }) {
  const api = useItsmApi();
  const [message, contextHolder] = antdMessage.useMessage();
  const [items, setItems] = useState<IntegrationItem[]>([]);
  const [text, setText] = useState(JSON.stringify(config.inputs || {}, null, 2));
  const [error, setError] = useState('');
  useEffect(() => { if (api.ready) void api.listIntegrations(true).then(value => setItems((value as { items: IntegrationItem[] }).items)).catch(() => message.error('加载集成失败')); }, [api.ready, api.listIntegrations, message]);
  return <>
    {contextHolder}
    <Select aria-label="选择集成" placeholder="选择 API 或 Python 集成" showSearch optionFilterProp="label" value={config.integration_id as number | undefined} options={items.filter(item => item.is_enabled && item.kind !== 'todo').map(item => ({ value: item.id, label: `${item.kind === 'api' ? 'API' : 'Python'} · ${item.name}` }))} onChange={integration_id => onChange({ ...config, integration_id })} />
    <Input.TextArea aria-label="集成输入参数" rows={7} value={text} status={error ? 'error' : undefined} onChange={event => { const value = event.target.value; setText(value); try { const inputs = parseInputs(value); setError(''); onChange({ ...config, inputs }); } catch { setError('请输入有效的 JSON 对象'); onChange({ ...config, inputs: null }); } }} />
    <Input aria-label="结果写入字段" placeholder="结果写入字段（可选）" value={String(config.result_field || '')} onChange={event => onChange({ ...config, result_field: event.target.value })} />
    {error && <Alert type="error" message={error} />}
    <span className="text-xs text-[var(--color-text-3)]">{'参数支持完整值引用，如 "${form.amount}"、"${ticket.sn}"。Python 输入使用 rows 和 params。'}</span>
  </>;
}
