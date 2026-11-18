'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmListTabs, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { useRouter } from 'next/navigation';
import { usePageLeave } from '../../components/page-leave';
import { ItsmBackButton } from '@/app/itsm/components/back-button';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiOutlined, CodeOutlined, InboxOutlined, PlayCircleOutlined, UploadOutlined } from '@ant-design/icons';
import { Alert, Button, Checkbox, Input, Select, Space, Spin, Switch, Tabs, Tag, Upload, message as antdMessage } from 'antd';
import CustomTable from '../../components/itsm-list-table';
import { FieldRow } from '../../components/field-row';
import { useItsmApi } from '../../api/useItsmApi';
import OpenApiDocsDetail from '@/app/system-manager/(pages)/settings/openapi-docs/OpenApiDocsDetail';
import { flattenOpenApiCatalog, generateSamplePayload } from '@/app/system-manager/utils/openapiDocs';
import type { OpenAPIDocsCatalog } from '@/app/system-manager/api/settings';
import { parseInputs, PYTHON_EXAMPLE, readPythonFile, type IntegrationItem, type IntegrationKind, type IntegrationResult } from './helpers';

const statuses: Record<string, string> = { running: '执行中', pending: '待投递', failed: '失败', done: '成功', superseded: '已被新状态替代' };

export default function IntegrationWorkspace({ integrationId, mode = "configure" }: { integrationId?: string; mode?: string }) {
  const router = useRouter();
  const [baseline,setBaseline]=useState('');
  const [pageError,setPageError]=useState('');
  const api = useItsmApi();
  const [message, contextHolder] = antdMessage.useMessage();
  const notifyError = useCallback((error: unknown) => { void message.error(error instanceof Error ? error.message : '操作失败'); }, [message]);
  const [items, setItems] = useState<IntegrationItem[]>([]);
  const [catalog, setCatalog] = useState<OpenAPIDocsCatalog>();
  const [kind, setKind] = useState<IntegrationKind>('api');
  useEffect(()=>{const saved=sessionStorage.getItem('itsm:integration:kind');if(saved && ['api','python','todo'].includes(saved))setKind(saved as IntegrationKind);setKeyword(sessionStorage.getItem('itsm:integration:search')||'');},[]);
  const [keyword, setKeyword] = useState('');
  const [permissions, setPermissions] = useState({ can_add: false, can_edit: false });
  const [draft, setDraft] = useState<IntegrationItem>();
  const [selected, setSelected] = useState<IntegrationItem>();
  const [input, setInput] = useState('{}');
  const [result, setResult] = useState<IntegrationResult>();
  const [busy, setBusy] = useState(false);
  const leave=usePageLeave(!!draft && JSON.stringify(draft)!==baseline);
  const [docTab, setDocTab] = useState('params');
  const rows = useMemo(() => flattenOpenApiCatalog(catalog), [catalog]);
  const endpoints = rows.filter(row => row.kind === 'internal');
  const endpoint = endpoints.find(row => row.path === `/openapi/v1/${draft?.config.path}` && row.method === draft?.config.method);

  const load = useCallback(async () => {
    const data = await api.listIntegrations() as { items: IntegrationItem[]; can_add: boolean; can_edit: boolean };
    setItems(data.items); setPermissions(data);
  }, [api.listIntegrations]);
  useEffect(() => { if (api.ready) void load().catch(notifyError); }, [api.ready, load, notifyError]);
  useEffect(() => {
    if (!api.ready || mode === 'records' || draft?.kind !== 'api') return;
    let live = true;
    void api.integrationCatalog().then(value => { if (live) setCatalog(value as OpenAPIDocsCatalog); }).catch(error => { if (live) notifyError(error); });
    return () => { live = false; };
  }, [api.ready, api.integrationCatalog, mode, draft?.kind, notifyError]);

  const patchConfig = (value: IntegrationItem['config']) => setDraft(current => current ? { ...current, config: { ...current.config, ...value } } : current);
  const save = async () => {
    if (!draft?.name.trim()) { message.warning('请输入集成名称'); return; }
    setBusy(true);
    try {
      const saved = await api.saveIntegration({ name: draft.name.trim(), kind: draft.kind, config: draft.config, is_enabled: draft.is_enabled }, draft.id || undefined);
      setBaseline(JSON.stringify(draft)); await load(); message.success('已保存');
      if (!draft.id) router.replace(`/itsm/form/integrations/${(saved as {id:number}).id}/configure`);
    } catch (error) { notifyError(error); } finally { setBusy(false); }
  };
  useEffect(()=>{
    if (!api.ready || !integrationId) return;
    let live=true;
    setDraft(undefined);setSelected(undefined);setPageError('');
    if (integrationId.startsWith('new-')) {
      const newKind=integrationId.slice(4) as IntegrationKind;
      if (!['api','python','todo'].includes(newKind)) {setPageError('未知集成类型');return;}
      const initial={id:0,name:'',kind:newKind,is_enabled:true,updated_by:'',config:newKind==='python'?{script:PYTHON_EXAMPLE,filename:'transform.py'}:{}};
      setDraft(initial);setBaseline(JSON.stringify(initial));
    } else {
      void api.getIntegration(Number(integrationId)).then(async value=>{
        if (!live) return;
        const detail=value as IntegrationItem;
        if (mode==='records') {
          setSelected(detail);setResult(undefined);
          const catalog=detail.kind === 'api' && detail.config.transport !== 'external' ? await api.integrationCatalog() as OpenAPIDocsCatalog : { services: [] };
          if(!live)return;
          const definition=flattenOpenApiCatalog(catalog).find(row=>row.path===`/openapi/v1/${detail.config.path}` && row.method===detail.config.method);
          const sample=detail.kind==='python'?{rows:[{amount:100}],params:{rate:2}}:detail.kind==='todo'?{event:'test',event_id:crypto.randomUUID(),title:'待办对接测试',assignees:[]}:generateSamplePayload(detail.config.transport==='external'?detail.config.request_schema:definition?.requestSchema)||{};
          setInput(JSON.stringify(sample,null,2));
        }
        else {setDraft(detail);setBaseline(JSON.stringify(detail));}
      }).catch(error=>{if(live)setPageError(error instanceof Error?error.message:'加载失败');});
    }
    return ()=>{live=false;};
  },[api.ready,integrationId,mode,api.getIntegration,api.integrationCatalog]);
  const test = async () => {
    if (!selected) return;
    setBusy(true); setResult(undefined);
    try { setResult(await api.testIntegration(selected.id, parseInputs(input)) as IntegrationResult); setSelected(await api.getIntegration(selected.id) as IntegrationItem); }
    catch (error) { notifyError(error); } finally { setBusy(false); }
  };

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    {contextHolder}
    {!integrationId && <><ItsmListToolbar leading={<ItsmListTabs activeKey={kind} onChange={value => {setKind(value as IntegrationKind);sessionStorage.setItem('itsm:integration:kind',value);}} items={[
      { key: 'api', label: <Space><ApiOutlined />API 集成</Space> },
      { key: 'python', label: <Space><CodeOutlined />Python 脚本</Space> },
      { key: 'todo', label: <Space><InboxOutlined />待办对接</Space> },
    ]} />} search={{value: keyword, onChange: value=>{setKeyword(value);sessionStorage.setItem('itsm:integration:search',value);}, label: '搜索集成', placeholder: '搜索名称或标识'}} actions={<>
{kind === 'api' && <Button href="/system-manager/settings/openapi-docs" target="_blank">平台 API 文档</Button>}
{permissions.can_add && <ItsmCreateButton onClick={() => router.push(`/itsm/form/integrations/new-${kind}/configure`)}>新建</ItsmCreateButton>}
</>} />
    <CustomTable storageKey="itsm:integration:position" queryKey={`${kind}:${keyword}`} rowKey="id" dataSource={items.filter(item => item.kind === kind && `${item.name} ${item.config.path || ''}`.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[
      { title: '名称', dataIndex: 'name', key: 'name', render: (value: string, item: IntegrationItem) => <ItsmListEntry href={`/itsm/form/integrations/${item.id}/configure`}>{value}</ItsmListEntry> },
      { title: kind === 'api' ? '接口地址' : kind === 'python' ? '文件' : '接收地址', key: 'target', render: (_: unknown, item: IntegrationItem) => item.config.path ? <span className="font-mono text-xs">{item.config.method} {item.config.path}</span> : item.config.filename || item.config.url },
      { title: '状态', key: 'enabled', render: (_: unknown, item: IntegrationItem) => <Tag color={item.is_enabled ? 'green' : 'default'}>{item.is_enabled ? '启用' : '停用'}</Tag> },
      { title: '维护人', dataIndex: 'updated_by', key: 'owner' },
      { fixed: 'right' as const, width: 120, title: '操作', key: 'actions', render: (_: unknown, item: IntegrationItem) => <ItsmRowActions items={[{key: 'action-0', label: permissions.can_edit ? '配置' : '查看', kind: 'configure' as const, onClick: () => router.push(`/itsm/form/integrations/${item.id}/configure`)},
        {key: 'action-1', label: permissions.can_edit ? '调试 / 记录' : '记录', kind: 'history' as const, onClick: () => router.push(`/itsm/form/integrations/${item.id}/records`)}]} /> },
    ]} />
    </>}
    {integrationId && <>
      <div className="sticky top-0 z-10 mb-4 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg)] pb-3">
        <div className="flex items-center gap-3"><ItsmBackButton label="返回集成列表" disabled={busy} onClick={()=>leave(()=>router.push('/itsm/form/integrations'))} /><span className="text-base font-semibold">{draft?.name || selected?.name || (integrationId.startsWith('new-')?'新建集成':'集成配置')}</span></div>
        <Space>{!integrationId.startsWith('new-') && <Button disabled={busy} onClick={()=>leave(()=>router.push(`/itsm/form/integrations/${integrationId}/${mode==='records'?'configure':'records'}`))}>{mode==='records'?'配置':'调试与记录'}</Button>}
        {draft && <Button type="primary" loading={busy} disabled={draft.id ? !permissions.can_edit : !permissions.can_add} onClick={()=>void save()}>保存</Button>}</Space>
      </div>
      {pageError && <Alert type="error" message={pageError} />}
      {!draft && !selected && !pageError && <div className="flex min-h-48 items-center justify-center"><Spin tip="加载集成"><div className="h-16 w-40" /></Spin></div>}
      <section aria-label="集成配置" className="mx-auto max-w-6xl">
      {draft && <div className="flex flex-col gap-4 py-3">
        <FieldRow label="名称"><Input aria-label="集成名称" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} maxLength={128} /></FieldRow>
        {draft.id > 0 && <FieldRow label="启用"><Switch checked={draft.is_enabled} onChange={is_enabled => setDraft({ ...draft, is_enabled })} /></FieldRow>}
        {draft.kind === 'api' && <>
          <FieldRow label="API 来源"><Select aria-label="API 来源" className="w-full" value={draft.config.transport || 'gateway'} options={[{value: 'gateway', label: '平台网关'}, {value: 'external', label: '外部 API'}]} onChange={transport => setDraft({ ...draft, config: transport === 'external' ? { transport, method: 'GET', url: '', request_schema: { type: 'object', properties: {} } } : { transport } })} /></FieldRow>
          {draft.config.transport === 'external' ? <>
            <FieldRow label="请求地址"><Input aria-label="外部 API 地址" value={draft.config.url} placeholder="https://api.example.com/items" onChange={e => patchConfig({ url: e.target.value })} /></FieldRow>
            <FieldRow label="请求方法"><Select aria-label="请求方法" className="w-full" value={draft.config.method || 'GET'} options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(value => ({value, label: value}))} onChange={method => patchConfig({method})} /></FieldRow>
            <FieldRow label="Bearer Token"><Input.Password aria-label="外部 API 认证令牌" autoComplete="new-password" value={draft.config.token} placeholder={draft.has_token ? '已配置，留空保留' : '可选；令牌加密保存'} onChange={e => patchConfig({token:e.target.value})} /></FieldRow>
            <FieldRow label="输入参数" align="start"><div className="flex w-full flex-col gap-2">
              {Object.entries(draft.config.request_schema?.properties || {}).map(([name, spec], index) => <div className="grid grid-cols-[1fr_110px_70px_1fr_90px] items-center gap-2" key={name}>
                <Input aria-label={`外部参数${index + 1}名称`} defaultValue={name} placeholder="参数名称" onBlur={e => { const next = e.target.value.trim(); if (next && next !== name && !(next in (draft.config.request_schema?.properties || {}))) patchConfig({request_schema: { ...draft.config.request_schema, required: (draft.config.request_schema?.required || []).map(k => k === name ? next : k), properties: Object.fromEntries(Object.entries(draft.config.request_schema?.properties || {}).map(([k,v]) => [k === name ? next : k,v])) }}); }} />
                <Select aria-label={`外部参数${index + 1}类型`} value={spec.type} options={['string','integer','number','boolean','array','object'].map(value => ({value,label: value}))} onChange={type => patchConfig({request_schema:{...draft.config.request_schema,properties:{...draft.config.request_schema?.properties,[name]:{...spec,type}}}})} />
                <Checkbox aria-label={`外部参数${index + 1}必填`} checked={draft.config.request_schema?.required?.includes(name)} onChange={e => patchConfig({request_schema: {...draft.config.request_schema, required: e.target.checked ? [...(draft.config.request_schema?.required || []), name] : (draft.config.request_schema?.required || []).filter(k => k !== name)}})}>必填</Checkbox>
                <Input aria-label={`外部参数${index + 1}说明`} placeholder="参数说明" value={spec.description} onChange={e => patchConfig({request_schema:{...draft.config.request_schema,properties:{...draft.config.request_schema?.properties,[name]:{...spec,description:e.target.value}}}})} />
                <Button onClick={() => patchConfig({request_schema:{...draft.config.request_schema,required:(draft.config.request_schema?.required || []).filter(k => k !== name),properties:Object.fromEntries(Object.entries(draft.config.request_schema?.properties || {}).filter(([k]) => k !== name))}})}>删除参数</Button>
              </div>)}
              <Button onClick={() => { const properties = draft.config.request_schema?.properties || {}; let n=1; while (`param_${n}` in properties) n++; patchConfig({request_schema:{...draft.config.request_schema,properties:{...properties,[`param_${n}`]:{type:'string'}}}}); }}>添加输入参数</Button>
            </div></FieldRow>
            <Alert type="info" showIcon message="外部接口须返回 JSON" description="GET 参数放在查询字符串，其他方法发送 JSON。保存后可在线调试，并在字段中选择此接口；字段只允许 GET 查询，流程 API 节点可使用其他方法。访问地址遵循平台网络白名单。" />
          </> : <><FieldRow label="平台接口"><Select className="w-full" aria-label="平台接口" showSearch optionFilterProp="label" placeholder="选择平台已注册的 API" value={endpoint?.key} options={endpoints.map(row => ({ value: row.key, label: `${row.method} ${row.path} · ${row.summary || row.service}` }))} onChange={key => { const row = endpoints.find(item => item.key === key); if (row) patchConfig({ method: row.method, path: row.path.replace('/openapi/v1/', '') }); }} /></FieldRow>
            {endpoint && <OpenApiDocsDetail selectedRow={endpoint} activeTab={docTab} onTabChange={setDocTab} />}
            <span className="text-xs text-[var(--color-text-3)]">接口定义、参数与权限来自平台 API 文档；在线调试会真实调用接口。</span>
          </>}
        </>}
        {draft.kind === 'python' && <>
          <FieldRow label="Python 文件"><Upload accept=".py" showUploadList={false} beforeUpload={async file => { try { patchConfig({ script: await readPythonFile(file), filename: file.name }); } catch (error) { notifyError(error); } return false; }}><Button icon={<UploadOutlined />}>上传 .py</Button></Upload><span className="ml-3 text-[var(--color-text-3)]">{draft.config.filename} · UTF-8 / 100KB</span></FieldRow>
          <FieldRow label="脚本" align="start"><Input.TextArea aria-label="Python 脚本" className="font-mono" rows={12} value={draft.config.script} onChange={event => patchConfig({ script: event.target.value })} /></FieldRow>
          <Alert type="info" showIcon message="复用平台隔离执行器" description="定义 transform(rows, params)，返回对象数组。可使用 json、math、datetime、collections；不支持文件系统或网络访问，执行超时会终止。" />
        </>}
        {draft.kind === 'todo' && <>
          <FieldRow label="接收地址"><Input aria-label="待办接收地址" value={draft.config.url} placeholder="https://example.com/todo/events" onChange={event => patchConfig({ url: event.target.value })} /></FieldRow>
          <FieldRow label="Bearer Token"><Input.Password aria-label="待办认证令牌" autoComplete="new-password" value={draft.config.token} placeholder={draft.has_token ? '已配置，留空保留' : '接收方要求认证时填写'} onChange={event => patchConfig({ token: event.target.value })} /></FieldRow>
          <Alert type="info" showIcon message="推送 ITSM 待办到外部系统" description="同步 create / update / close 事件、处理人和工单链接。接收方按 task_id 更新待办、使用 event_id 去重，并返回 2xx；失败可在记录中重试。测试工单不会向外推送。" />
        </>}
      </div>}
    </section>
    {selected && <section aria-label="调试与记录">
      <Tabs items={[
        { key: 'debug', label: '在线调试', children: <div className="flex flex-col gap-3">
          <Input.TextArea aria-label="调试参数" value={input} onChange={event => setInput(event.target.value)} rows={9} className="font-mono" />
          <div><Button type="primary" aria-label="执行测试" icon={<PlayCircleOutlined />} loading={busy} disabled={!permissions.can_edit || !selected?.is_enabled} onClick={() => void test()}>执行测试</Button><span className="ml-3 text-xs text-[var(--color-text-3)]">使用当前用户权限执行；API 与待办测试会产生真实请求。</span></div>
          {result && <><Alert showIcon type={result.status === 'done' ? 'success' : 'error'} message={`${statuses[result.status]} · ${result.duration_ms} ms${result.code ? ` · ${result.code}` : ''}`} /><pre className="max-h-72 overflow-auto rounded bg-[var(--color-fill-2)] p-3 text-xs">{JSON.stringify(result.output, null, 2)}</pre></>}
        </div> },
        { key: 'runs', label: '执行记录', children: <CustomTable rowKey="id" dataSource={selected?.runs || []} columns={[
          { title: '时间', dataIndex: 'created_at', key: 'time' }, { title: '操作者', dataIndex: 'created_by', key: 'user' },
          { title: '状态', key: 'status', render: (_: unknown, row: { status: string; code: string }) => `${statuses[row.status] || row.status} ${row.code}` }, { title: '耗时（ms）', dataIndex: 'duration_ms', key: 'duration' },
        ]} /> },
        ...(selected?.kind === 'todo' ? [{ key: 'deliveries', label: '待办投递', children: <CustomTable<NonNullable<IntegrationItem['deliveries']>[number]> rowKey="id" dataSource={selected.deliveries || []} columns={[
          { title: '任务', dataIndex: 'task_id', key: 'task' }, { title: '状态', key: 'status', render: (_: unknown, row: { status: string; code: string }) => `${statuses[row.status] || row.status} ${row.code}` },
          { title: '次数', dataIndex: 'attempts', key: 'attempts' }, { fixed: 'right' as const, width: 120, title: '操作', key: 'action', render: (_: unknown, row: { id: number; status: string }) => <ItsmRowActions items={(row.status === 'failed' && permissions.can_edit ? [{key: 'action-2', label: "重试", kind: 'retry' as const, onClick: () => { void api.retryDelivery(selected.id, row.id).then(() => api.getIntegration(selected.id)).then(value => setSelected(value as IntegrationItem)).catch(notifyError); }}] : [])} /> },
        ]} /> }] : []),
      ]} />
    </section>}
    </>}
  </div>;
}
