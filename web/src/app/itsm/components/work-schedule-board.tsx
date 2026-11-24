'use client';

import { Input, message, type TableColumnsType } from 'antd';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { FieldRow } from './field-row';
import { ItsmModal } from './interaction-surfaces';
import ItsmListTable from './itsm-list-table';
import { ItsmCreateButton, ItsmListToolbar, ItsmRowActions } from './list-controls';
import { ItsmListEntry } from './list-entry';

interface ScheduleRow {
  id: number;
  name: string;
}

interface WorkScheduleBoardProps<Row extends ScheduleRow, Draft extends { name: string }> {
  kind: 'changes' | 'duties';
  title: string;
  columns: TableColumnsType<Row>;
  toDraft: (row?: Row) => Draft;
  toPayload: (draft: Draft) => Record<string, unknown>;
  renderFields: (draft: Draft, setDraft: (draft: Draft) => void) => ReactNode;
  searchValues: (row: Row) => string[];
  view?: {
    key: string;
    leading?: ReactNode;
    filters?: ReactNode;
    includes?: (row: Row) => boolean;
    newDraft?: Partial<Draft>;
    render?: (options: {
      rows: Row[];
      loading: boolean;
      create?: () => void;
      edit?: (row: Row) => void;
    }) => ReactNode;
  };
}

interface ScheduleList<Row> {
  items: Row[];
  can_add?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
}

export function WorkScheduleBoard<Row extends ScheduleRow, Draft extends { name: string }>({
  kind, title, columns, toDraft, toPayload, renderFields, searchValues, view,
}: WorkScheduleBoardProps<Row, Draft>) {
  const api = useItsmApi();
  const [list, setList] = useState<ScheduleList<Row>>({ items: [] });
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<Draft>();
  const [editingId, setEditingId] = useState<number>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setList(await api.listResources(kind) as ScheduleList<Row>);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [api.listResources, kind]);

  useEffect(() => {
    if (api.ready) void load();
  }, [api.ready, load]);

  const open = (row?: Row) => {
    setEditingId(row?.id);
    setDraft(row ? toDraft(row) : { ...toDraft(), ...view?.newDraft });
  };

  const save = async () => {
    if (!draft) return;
    const name = draft.name.trim();
    if (!name) throw new Error('请输入名称');
    const payload = toPayload({ ...draft, name });
    if (editingId === undefined) {
      await api.createResource(kind, payload);
    } else {
      await api.updateResource(kind, editingId, payload);
    }
    setDraft(undefined);
    message.success('已保存');
    await load();
  };

  const remove = async (id: number) => {
    try {
      await api.deleteResource(kind, id);
      message.success('已删除');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败');
    }
  };

  const tableColumns: TableColumnsType<Row> = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, row: Row) => list.can_edit ? <ItsmListEntry onClick={() => open(row)}>{name}</ItsmListEntry> : name,
    },
    ...columns,
  ];
  if (list.can_edit || list.can_delete) {
    tableColumns.push({
      title: '操作', key: 'actions', width: 120, fixed: 'right',
      render: (_, row) => <ItsmRowActions items={[
        { key: 'edit', kind: 'edit', label: '编辑', hidden: !list.can_edit, onClick: () => open(row) },
        { key: 'delete', kind: 'delete', label: '删除', hidden: !list.can_delete, danger: true,
          confirm: { title: `删除${title}「${row.name}」？` }, onClick: () => void remove(row.id) },
      ]} />,
    });
  }
  const query = keyword.trim().toLowerCase();
  const filtered = list.items.filter(row => (!view?.includes || view.includes(row))
    && (!query || [row.name, ...searchValues(row)].some(value => value.toLowerCase().includes(query))));
  const create = list.can_add ? () => open() : undefined;
  const content = view?.render
    ? view.render({ rows: filtered, loading, create, edit: list.can_edit ? open : undefined })
    : <ItsmListTable<Row> rowKey="id" queryKey={view ? `${view.key}:${keyword}` : keyword} loading={loading}
        dataSource={filtered} columns={tableColumns} locale={{ emptyText: `暂无${title}` }} />;

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar leading={view?.leading} filters={view?.filters}
      search={{ value: keyword, onChange: setKeyword, placeholder: `搜索${title}` }}
      actions={create && <ItsmCreateButton onClick={create}>{`新建${title}`}</ItsmCreateButton>} />
    {content}
    <ItsmModal title={`${editingId === undefined ? '新建' : '编辑'}${title}`} open={!!draft} formValue={draft}
      onOk={save} onCancel={() => setDraft(undefined)}>
      {draft && <div className="flex flex-col gap-4">
        <FieldRow label="名称"><Input aria-label="名称" required maxLength={128} value={draft.name}
          onChange={event => setDraft({ ...draft, name: event.target.value })} /></FieldRow>
        {renderFields(draft, setDraft)}
      </div>}
    </ItsmModal>
  </div>;
}
