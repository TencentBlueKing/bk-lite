'use client';

import { useEffect, useId, useState } from 'react';
import { Alert, Button, Input, Pagination, Table } from 'antd';
import { useItsmApi } from '../../api/useItsmApi';
import { ItsmModal } from '../../components/interaction-surfaces';
import { UserSelector } from '../../components/user-selector';
import type { HandoverCandidate, HandoverRecord } from '../../types';

const PAGE_SIZE = 20;
const MAX_TICKETS = 50;

export function HandoverForm({ onCreated, onClose }: {
  onCreated: (record: HandoverRecord) => void;
  onClose: () => void;
}) {
  const { searchHandoverCandidates, createHandover } = useItsmApi();
  const fromId = useId();
  const toId = useId();
  const [fromUser, setFromUser] = useState('');
  const [toUser, setToUser] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState({ keyword: '', page: 1 });
  const [result, setResult] = useState<{
    query: typeof query;
    fromUser: string;
    items: HandoverCandidate[];
    count: number;
    failed?: boolean;
  }>();
  const page = result?.query === query && result.fromUser === fromUser ? result : undefined;
  const loading = Boolean(fromUser && !page);

  useEffect(() => {
    if (!fromUser) return;
    let active = true;
    void searchHandoverCandidates(fromUser, query.keyword, query.page).then(result => {
      if (active) setResult({ ...result, query, fromUser });
    }).catch(() => {
      if (active) setResult({ query, fromUser, count: 0, items: [], failed: true });
    });
    return () => { active = false; };
  }, [fromUser, query, searchHandoverCandidates]);

  const changeSource = ([username = '']: string[]) => {
    setFromUser(username);
    setSelected([]);
    setSearch('');
    setQuery({ keyword: '', page: 1 });
  };
  const sameUser = Boolean(fromUser && fromUser === toUser);
  const overLimit = selected.length > MAX_TICKETS;
  const canSubmit = Boolean(fromUser && toUser && selected.length && !sameUser && !overLimit);

  return <ItsmModal open title="新建交接" width={760} okText="确认交接" onCancel={onClose}
    formValue={{ fromUser, toUser, selected }} okButtonProps={{ disabled: !canSubmit }} onOk={async () => {
      if (!canSubmit) return;
      onCreated(await createHandover({ from_user: fromUser, to_user: toUser, ticket_ids: selected }));
    }}>
    <div className="flex flex-col gap-4 py-2">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label htmlFor={fromId}>交出人</label>
          <UserSelector id={fromId} ariaLabel="交出人" placeholder="选择交出人" multiple={false} allowClear
            value={fromUser ? [fromUser] : []} onChange={changeSource} />
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor={toId}>接收人</label>
          <UserSelector id={toId} ariaLabel="接收人" placeholder="选择接收人" multiple={false} allowClear
            value={toUser ? [toUser] : []} onChange={([username = '']) => setToUser(username)} />
        </div>
      </div>
      {sameUser && <Alert type="warning" showIcon message="请选择不同的交出人和接收人" />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>已选 {selected.length} 张工单</span>
        <Input.Search className="w-64 max-w-full" aria-label="搜索待办工单" placeholder="搜索单号或标题" allowClear
          disabled={!fromUser} value={search} onChange={event => setSearch(event.target.value)}
          onSearch={value => setQuery({ keyword: value.trim(), page: 1 })} />
      </div>
      {overLimit && <Alert type="warning" showIcon message={`一次最多交接 ${MAX_TICKETS} 张工单，请减少已选工单`} />}
      {page?.failed && <Alert type="error" showIcon message="待办工单加载失败"
        action={<Button size="small" onClick={() => setQuery({ ...query })}>重新加载</Button>} />}
      <Table<HandoverCandidate> rowKey="id" size="small" loading={loading} dataSource={page?.items || []}
        scroll={{ y: 300 }} pagination={false}
        locale={{ emptyText: fromUser ? (page?.failed ? '加载失败' : '没有匹配的待办工单') : '请先选择交出人' }}
        rowSelection={{
          selectedRowKeys: selected,
          preserveSelectedRowKeys: true,
          onChange: keys => setSelected(keys.map(Number)),
          getCheckboxProps: item => ({ title: `选择 ${item.sn}`, 'aria-label': `选择 ${item.sn}` }),
        }}
        columns={[
          { title: '单号', dataIndex: 'sn', width: 176 },
          { title: '标题', dataIndex: 'title', ellipsis: true },
        ]} />
      {page && page.count > PAGE_SIZE && <Pagination className="self-end" size="small" current={query.page}
        total={page.count} pageSize={PAGE_SIZE} showSizeChanger={false}
        onChange={next => setQuery({ ...query, page: next })} />}
    </div>
  </ItsmModal>;
}
