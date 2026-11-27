'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, Table, Tag } from 'antd';
import { ItsmModal } from '../../components/interaction-surfaces';
import { useItsmApi, type JobParameter, type WorkflowJobOptions } from '../../api/useItsmApi';
import ItsmListTable from '../../components/itsm-list-table';

type Script = WorkflowJobOptions['scripts'][number];

export function JobCatalog({ keyword }: { keyword: string }) {
  const { ready, integrationJobCatalog } = useItsmApi();
  const [catalog, setCatalog] = useState<WorkflowJobOptions & { can_execute: boolean }>();
  const [detail, setDetail] = useState<Script>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    integrationJobCatalog().then(data => {
      if (active) setCatalog(data);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : '读取作业目录失败');
    });
    return () => { active = false; };
  }, [ready, integrationJobCatalog, attempt]);

  if (error) return <Alert type="error" showIcon message={error} action={
    <Button size="small" onClick={() => { setError(''); setAttempt(value => value + 1); }}>重试</Button>
  } />;
  const query = keyword.trim().toLowerCase();
  return <>
    {catalog && <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-sm text-[var(--color-text-2)]">可选执行目标（{catalog.targets.length}）</span>
      {catalog.targets.map(target => <Tag key={target.id} className="m-0">{target.name}</Tag>)}
    </div>}
    <ItsmListTable<Script> rowKey="id" loading={!catalog} queryKey={query}
      dataSource={catalog?.scripts.filter(script => `${script.name} ${script.id}`.toLowerCase().includes(query)) || []}
      columns={[
        { title: '作业名称', dataIndex: 'name', key: 'name' },
        { title: '作业 ID', dataIndex: 'id', key: 'id', width: 110 },
        { title: '用途', dataIndex: 'description', key: 'description', render: text => text || '—' },
        { title: '输入参数', key: 'params', render: (_, script) => script.params.length
          ? <Button type="link" size="small" onClick={() => setDetail(script)}>查看参数（{script.params.length}）</Button>
          : '无' },
        ...(catalog?.can_execute ? [{
          title: '操作', key: 'action', width: 120, render: (_: unknown, script: Script) => (
            <Button type="link" size="small" href={`/job/execution/quick-exec?script_id=${script.id}&mode=test`} target="_blank" rel="noopener noreferrer">测试作业</Button>
          ),
        }] : []),
      ]} />
    <ItsmModal title={`${detail?.name || ''} · 输入参数`} open={!!detail} width={900} footer={null} onCancel={() => setDetail(undefined)}>
      <Table<JobParameter> rowKey="name" size="small" pagination={false} scroll={{ x: 700 }} dataSource={detail?.params} columns={[
        { title: '名称', key: 'label', render: (_, p) => p.label || p.name },
        { title: '标识（Key）', dataIndex: 'name', key: 'name', render: name => <code>{name}</code> },
        { title: '用途说明', dataIndex: 'description', key: 'description', render: text => text || '—' },
        { title: '类型', dataIndex: 'type', key: 'type', render: type => type === 'enum' ? '枚举' : '文本' },
        { title: '必填', dataIndex: 'is_required', key: 'required', render: required => required ? '是' : '否' },
        { title: '枚举选项', key: 'options', render: (_, p) => p.type === 'enum' ? p.options?.join('、') || '—' : '—' },
      ]} />
    </ItsmModal>
  </>;
}
