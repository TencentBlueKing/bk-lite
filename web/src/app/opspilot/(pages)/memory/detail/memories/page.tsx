'use client';

import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useMemoryApi, Memory } from '@/app/opspilot/api/memory';
import { Table, Select, Button, message, Input, Popconfirm } from 'antd';
import PermissionWrapper from '@/components/permission';
import MarkdownRenderer from '@/components/markdown';
import { useMemoryContext } from '../layout';

export default function MemoriesPage() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { fetchMemories, updateMemory, deleteMemory } = useMemoryApi();
  const { space } = useMemoryContext();
  
  const idStr = searchParams.get('id');
  const id = idStr ? parseInt(idStr, 10) : 0;

  // Determine if this is a team memory space
  const isTeamScope = space?.scope === 'team';

  const [loading, setLoading] = useState(false);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedUser, setSelectedUser] = useState<string | undefined>(undefined);

  // Preview & Edit states
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    if (id) {
      loadMemories();
    }
  }, [id]);

  const loadMemories = async () => {
    setLoading(true);
    try {
      const res = await fetchMemories(id);
      setMemories(res);
      if (res.length > 0 && !selectedId) {
        setSelectedId(res[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const selectedMemory = memories.find(m => m.id === selectedId);

  const handleSave = async () => {
    if (!selectedMemory) return;
    setSaving(true);
    try {
      await updateMemory(selectedMemory.id, { content: editContent });
      message.success(t('memory.saveSuccess'));
      setMemories(memories.map(m => m.id === selectedMemory.id ? { ...m, content: editContent } : m));
      setEditing(false);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    if (selectedMemory) {
      setEditContent(selectedMemory.content);
      setEditing(true);
    }
  };

  const handleCancel = () => {
    setEditing(false);
    setEditContent('');
  };

  const handleDelete = async (memoryId: number) => {
    try {
      await deleteMemory(memoryId);
      message.success(t('common.deleteSuccess'));
      const newMemories = memories.filter(m => m.id !== memoryId);
      setMemories(newMemories);
      if (selectedId === memoryId) {
        setSelectedId(newMemories.length > 0 ? newMemories[0].id : null);
      }
    } catch (e) {
      console.error(e);
      message.error(t('common.deleteFailed'));
    }
  };

  const handleView = (memoryId: number) => {
    setSelectedId(memoryId);
    setEditing(false);
  };

  const users = Array.from(new Set(memories.map(m => m.owner_username)));
  const filteredMemories = selectedUser 
    ? memories.filter(m => m.owner_username === selectedUser)
    : memories;

  return (
    /* 响应式:小屏单列堆叠,lg(≥1024px)及以上恢复 6:4 双列。
       h-full 改为 lg:h-full,小屏让出自然高度,触发 sub-layout .sectionContext
       overflow-auto 出滚动条;大屏撑满让 list 表格 / preview textarea 拿高度。
       详见 config 页同款注释。 */
    <div className="grid grid-cols-1 gap-4 lg:h-full lg:grid-cols-10">
      {/* Left: Memory List - 6/10 on large screens */}
      <section className="border border-(--color-border-1) rounded-[10px] bg-(--color-bg) min-h-0 flex flex-col overflow-hidden lg:col-span-6">
        {/* Outer card header */}
        <div className="h-10 border-b border-(--color-border-1) px-4 flex items-center bg-(--color-fill-1) shrink-0">
          <span className="text-[13px] font-bold text-(--color-text-1)">{t('memory.memoryList')}</span>
        </div>

        {/* Inner content with table header */}
        <div className="flex-1 min-h-0 flex flex-col p-3">
          <div className="border border-(--color-border-1) rounded-lg flex-1 flex flex-col overflow-hidden">
            {/* Table header with filter */}
            <div className="h-10 border-b border-(--color-border-1) px-3 flex items-center justify-between bg-(--color-bg) shrink-0">
              <span className="text-[13px] font-semibold text-(--color-text-1)">{t('memory.memoryList')}</span>
              <Select
                allowClear
                placeholder={isTeamScope ? t('memory.filterOrganization') : t('memory.filterUser')}
                value={selectedUser}
                onChange={setSelectedUser}
                className="w-[140px] [&>.ant-select-selector]:rounded-md [&>.ant-select-selector]:border-[var(--color-border-1)] [&>.ant-select-selector]:bg-[var(--color-bg)] text-[12px] [&>.ant-select-selector]:h-[30px]"
              >
                {users.map(u => (
                  <Select.Option key={u} value={u}>{u}</Select.Option>
                ))}
              </Select>
            </div>

            {/* Table */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              <Table
                dataSource={filteredMemories}
                rowKey="id"
                loading={loading}
                pagination={false}
                size="small"
                className="[&_.ant-table]:bg-transparent [&_.ant-table-thead>tr>th]:bg-(--color-fill-1) [&_.ant-table-thead>tr>th]:text-(--color-text-3) [&_.ant-table-thead>tr>th]:font-semibold [&_.ant-table-thead>tr>th]:text-[12px] [&_.ant-table-thead>tr>th]:border-b [&_.ant-table-thead>tr>th]:border-(--color-border-1) [&_.ant-table-tbody>tr>td]:text-[12px] [&_.ant-table-tbody>tr>td]:text-(--color-text-2) [&_.ant-table-tbody>tr>td]:border-b [&_.ant-table-tbody>tr>td]:border-(--color-border-1) [&_.ant-table-tbody>tr]:hover:bg-(--color-fill-1)"
                columns={[
                  {
                    title: isTeamScope ? t('memory.organization') : t('memory.user'),
                    dataIndex: 'owner_username',
                    key: 'owner_username',
                    width: 100,
                    ellipsis: true
                  },
                  {
                    title: t('memory.memoryId'),
                    dataIndex: 'id',
                    key: 'id',
                    width: 80,
                    render: (val) => `m-${val}`
                  },
                  {
                    title: t('memory.updatedAt'),
                    dataIndex: 'updated_at',
                    key: 'updated_at',
                    width: 130,
                    render: (val) => {
                      const d = new Date(val);
                      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
                    }
                  },
                  {
                    title: t('memory.summary'),
                    dataIndex: 'content',
                    key: 'content',
                    ellipsis: true,
                    render: (val) => (
                      <span className="text-[var(--color-primary)]">
                        {val?.substring(0, 50)}...
                      </span>
                    )
                  },
                  {
                    title: t('common.actions'),
                    key: 'actions',
                    width: 100,
                    render: (_, record) => (
                      <div className="flex gap-2">
                        <Button
                          type="link"
                          className="text-[var(--color-primary)] text-[12px] p-0 h-auto"
                          onClick={() => handleView(record.id)}
                        >
                          {t('common.view')}
                        </Button>
                        <PermissionWrapper requiredPermissions={['Delete']}>
                          <Popconfirm
                            title={t('memory.deleteConfirm')}
                            onConfirm={() => handleDelete(record.id)}
                            okText={t('common.confirm')}
                            cancelText={t('common.cancel')}
                          >
                            <Button
                              type="link"
                              className="text-[var(--ant-color-error)] text-[12px] p-0 h-auto"
                            >
                              {t('common.delete')}
                            </Button>
                          </Popconfirm>
                        </PermissionWrapper>
                      </div>
                    )
                  }
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Right: Memory Preview - 4/10 on large screens */}
      <aside className="border border-(--color-border-1) rounded-[10px] bg-(--color-bg) min-h-0 flex flex-col overflow-hidden lg:col-span-4">
        {/* Header */}
        <div className="h-10 border-b border-(--color-border-1) px-4 flex items-center justify-between bg-(--color-fill-1) shrink-0">
          <span className="text-[13px] font-bold text-(--color-text-1)">{t('memory.preview')}</span>
          {selectedMemory && !editing && (
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                onClick={handleEdit}
                className="text-[var(--color-primary)] text-[12px] h-7 px-2 p-0"
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
          )}
          {editing && (
            <div className="flex gap-2">
              <Button
                type="link"
                onClick={handleCancel}
                className="text-(--color-text-3) text-[12px] h-7 px-2 p-0"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="primary"
                loading={saving}
                onClick={handleSave}
                className="bg-[var(--color-primary)] text-white text-[12px] h-7 px-3 rounded-md border-0 hover:opacity-90"
              >
                {t('common.save')}
              </Button>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 p-4 overflow-y-auto">
          {selectedMemory ? (
            editing ? (
              <Input.TextArea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                className="h-full resize-none rounded-lg border-(--color-border-1) bg-(--color-fill-1) p-3 text-[13px] font-mono text-(--color-text-2)"
                style={{ minHeight: '100%' }}
              />
            ) : (
              <div className="prose dark:prose-invert max-w-none text-[13px] text-(--color-text-2) leading-relaxed">
                <MarkdownRenderer content={selectedMemory.content || ''} />
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-[13px] text-(--color-text-3)">
              {t('memory.noMemories')}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
