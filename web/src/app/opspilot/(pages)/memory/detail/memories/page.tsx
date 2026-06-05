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
    <div className="flex gap-4 h-full">
      {/* Left: Memory List - flex-[6] for 6:4 ratio */}
      <section className="flex-[6] border border-[#dde5f0] dark:border-gray-800 rounded-[10px] bg-white dark:bg-[#252830] min-h-0 flex flex-col overflow-hidden">
        {/* Outer card header */}
        <div className="h-10 border-b border-[#e7edf6] dark:border-gray-800 px-4 flex items-center bg-[#f7f9fc] dark:bg-gray-800 shrink-0">
          <span className="text-[13px] font-bold text-[#314660] dark:text-gray-200">{t('memory.memoryList')}</span>
        </div>

        {/* Inner content with table header */}
        <div className="flex-1 min-h-0 flex flex-col p-3">
          <div className="border border-[#e7edf6] dark:border-gray-700 rounded-lg flex-1 flex flex-col overflow-hidden">
            {/* Table header with filter */}
            <div className="h-10 border-b border-[#e7edf6] dark:border-gray-700 px-3 flex items-center justify-between bg-white dark:bg-[#252830] shrink-0">
              <span className="text-[13px] font-semibold text-[#314660] dark:text-gray-200">{t('memory.memoryList')}</span>
              <Select
                allowClear
                placeholder={isTeamScope ? t('memory.filterOrganization') : t('memory.filterUser')}
                value={selectedUser}
                onChange={setSelectedUser}
                className="w-[140px] [&>.ant-select-selector]:rounded-md [&>.ant-select-selector]:border-[#d5dce6] dark:[&>.ant-select-selector]:border-gray-700 dark:bg-[#1a1c21] text-[12px] [&>.ant-select-selector]:h-[30px]"
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
                className="[&_.ant-table]:bg-transparent [&_.ant-table-thead>tr>th]:bg-[#fafbfc] dark:[&_.ant-table-thead>tr>th]:bg-[#1f2128] [&_.ant-table-thead>tr>th]:text-[#5c6d84] dark:[&_.ant-table-thead>tr>th]:text-gray-400 [&_.ant-table-thead>tr>th]:font-semibold [&_.ant-table-thead>tr>th]:text-[12px] [&_.ant-table-thead>tr>th]:border-b [&_.ant-table-thead>tr>th]:border-[#e7edf6] dark:[&_.ant-table-thead>tr>th]:border-gray-700 [&_.ant-table-tbody>tr>td]:text-[12px] [&_.ant-table-tbody>tr>td]:text-[#3d4f6a] dark:[&_.ant-table-tbody>tr>td]:text-gray-300 [&_.ant-table-tbody>tr>td]:border-b [&_.ant-table-tbody>tr>td]:border-[#e7edf6] dark:[&_.ant-table-tbody>tr>td]:border-gray-700 [&_.ant-table-tbody>tr]:hover:bg-[#f5f8ff] dark:[&_.ant-table-tbody>tr]:hover:bg-gray-800"
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
                      <span className="text-[#2b5bff] dark:text-blue-400">
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
                          className="text-[#2b5bff] text-[12px] p-0 h-auto"
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
                              className="text-[#ff4d4f] text-[12px] p-0 h-auto"
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

      {/* Right: Memory Preview - flex-[4] for 6:4 ratio */}
      <aside className="flex-[4] border border-[#dde5f0] dark:border-gray-800 rounded-[10px] bg-white dark:bg-[#252830] min-h-0 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="h-10 border-b border-[#e7edf6] dark:border-gray-800 px-4 flex items-center justify-between bg-[#f7f9fc] dark:bg-gray-800 shrink-0">
          <span className="text-[13px] font-bold text-[#314660] dark:text-gray-200">{t('memory.preview')}</span>
          {selectedMemory && !editing && (
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button 
                type="link" 
                onClick={handleEdit} 
                className="text-[#2b5bff] text-[12px] h-7 px-2 p-0"
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
                className="text-[#6b7d95] dark:text-gray-400 text-[12px] h-7 px-2 p-0"
              >
                {t('common.cancel')}
              </Button>
              <Button 
                type="primary" 
                loading={saving} 
                onClick={handleSave} 
                className="bg-[#2b5bff] text-white text-[12px] h-7 px-3 rounded-md border-0 hover:bg-[#1f4eeb]"
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
                className="h-full resize-none rounded-lg border-[#d5dce6] dark:border-gray-700 bg-[#fafbfc] dark:bg-[#1a1c21] p-3 text-[13px] font-mono text-[#3d4f6a] dark:text-gray-300"
                style={{ minHeight: '100%' }}
              />
            ) : (
              <div className="prose dark:prose-invert max-w-none text-[13px] text-[#3d4f6a] dark:text-gray-300 leading-relaxed">
                <MarkdownRenderer content={selectedMemory.content || ''} />
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-[13px] text-[#8a98ad] dark:text-gray-500">
              {t('memory.noMemories')}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
