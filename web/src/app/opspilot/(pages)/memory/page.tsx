'use client';

import React, {useCallback, useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {Button, Form, Input, message, Modal, Spin} from 'antd';
import {PlusOutlined} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import {useTranslation} from '@/utils/i18n';
import {MemorySpace, useMemoryApi} from '@/app/opspilot/api/memory';
import {useUserInfoContext} from '@/context/userInfo';

const { Search } = Input;

const MemoryPage = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { fetchMemorySpaces, createMemorySpace, updateMemorySpace, deleteMemorySpace } = useMemoryApi();
  const { selectedGroup } = useUserInfoContext();
  const [loading, setLoading] = useState(true);
  const [spaces, setSpaces] = useState<MemorySpace[]>([]);
  const [filteredSpaces, setFilteredSpaces] = useState<MemorySpace[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingSpace, setEditingSpace] = useState<MemorySpace | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [form] = Form.useForm();

  const loadSpaces = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchMemorySpaces();
      const items = Array.isArray(data) ? data : ((data as any).items || []);
      setSpaces(items);
      setFilteredSpaces(items);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadSpaces();
  }, [loadSpaces]);

  useEffect(() => {
    if (searchTerm) {
      setFilteredSpaces(spaces.filter(s => s.name.toLowerCase().includes(searchTerm.toLowerCase())));
    } else {
      setFilteredSpaces(spaces);
    }
  }, [searchTerm, spaces]);

  const handleAdd = () => {
    setEditingSpace(null);
    form.resetFields();
    form.setFieldsValue({
      scope: 'team',
      team: selectedGroup?.id ? [selectedGroup.id] : [],
    });
    setIsModalVisible(true);
  };

  const handleEdit = (space: MemorySpace) => {
    setEditingSpace(space);
    form.setFieldsValue({
      name: space.name,
      introduction: space.introduction,
      scope: space.scope,
      team: space.team || [],
    });
    setIsModalVisible(true);
  };

  const handleDelete = (space: MemorySpace) => {
    Modal.confirm({
      title: t('memory.deleteConfirm'),
      onOk: async () => {
        try {
          await deleteMemorySpace(space.id);
          message.success(t('common.delSuccess'));
          loadSpaces();
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);
      if (editingSpace) {
        await updateMemorySpace(editingSpace.id, values);
        message.success(t('common.updateSuccess'));
      } else {
        await createMemorySpace(values);
        message.success(t('common.addSuccess'));
      }
      setIsModalVisible(false);
      loadSpaces();
    } catch {
      // validation failed or api failed
    } finally {
      setConfirmLoading(false);
    }
  };

  
  const formFields = [
    {
      name: 'name',
      label: t('memory.name'),
      type: 'input' as const,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('memory.name')}` }],
    },
    {
      name: 'scope',
      label: t('memory.scope'),
      type: 'select' as const,
      options: [
        { label: t('memory.personal'), value: 'personal' },
        { label: t('memory.team'), value: 'team' },
      ],
      rules: [{ required: true }],
      initialValue: 'personal',
      disabled: !!editingSpace,
    },
    ...[
      {
        name: 'team',
        label: t('memory.organization'),
        type: 'groupTreeSelect' as const,
        rules: [{ required: true, message: `${t('common.selectMsg')}${t('memory.organization')}` }],
      }
    ],
    {
      name: 'introduction',
      label: t('memory.introduction'),
      type: 'textarea' as const,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('memory.introduction')}` }],
    },
  ];

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-4">
        <div className="flex flex-col">
          <h2 className="text-lg font-bold text-(--color-text-1)">{t('memory.memoryList')}</h2>
          <p className="text-sm text-(--color-text-3)">
            卡片代表一个可被工作流绑定和持续回写的记忆容器。
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Search
            placeholder="搜索记忆名称"
            allowClear
            onSearch={(value) => setSearchTerm(value)}
            onChange={(e) => !e.target.value && setSearchTerm('')}
            style={{ width: 200 }}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              {t('memory.createMemory')}
            </Button>
          </PermissionWrapper>
        </div>
      </div>

      <Spin spinning={loading}>
        <div className="grid grid-cols-4 gap-2.5">
          {filteredSpaces.map((space) => (
            <div
              key={space.id}
              className="relative flex flex-col cursor-pointer border border-(--color-border-1) rounded-xl bg-(--color-bg) h-[216px] transition-all duration-200 hover:-translate-y-px hover:shadow-[0_10px_20px_rgba(20,38,70,0.12)] hover:border-(--color-border-2) overflow-hidden"
              onClick={() => router.push(`/opspilot/memory/detail/config?id=${space.id}`)}
            >
              <div
                className={`relative flex-shrink-0 h-[56px] border-b border-(--color-border-1) ${
                  space.scope === 'team'
                    ? 'bg-gradient-to-br from-[#1e4fff] to-[#33a0ff]'
                    : 'bg-gradient-to-br from-[#d6e1f4] via-[#bed1f1] to-[#95b3ed]'
                }`}
              >
                <span 
                  className={`absolute left-3 top-3 h-5 px-2 rounded flex items-center text-xs font-medium backdrop-blur-md shadow-none ${
                    space.scope === 'team'
                      ? 'text-white bg-white/20'
                      : 'text-[#5977a5] bg-white/60'
                  }`}
                >
                  {space.scope === 'team' ? t('memory.team') : t('memory.personal')}
                </span>
                
                <div className="absolute right-2 top-2" onClick={(e) => e.stopPropagation()}>
                  <MoreActionsDropdown
                    items={[
                      {
                        key: 'edit',
                        label: t('common.edit'),
                        permission: 'Edit',
                        onClick: () => handleEdit(space),
                      },
                      {
                        key: 'delete',
                        label: t('common.delete'),
                        permission: 'Delete',
                        onClick: () => handleDelete(space),
                      },
                    ]}
                    buttonClassName="w-6 h-6 flex items-center justify-center rounded text-white/80 hover:text-white hover:bg-black/10 transition-colors"
                    iconStyle={{ fontSize: '18px' }}
                    placement="bottomRight"
                  />
                </div>
              </div>
              
              <div className="flex-1 p-[18px] flex flex-col min-h-0">
                <div className="flex-1 min-h-0">
                  <h3 className="text-[15px] font-bold text-(--color-text-1) mb-1.5 truncate">
                    {space.name}
                  </h3>
                  <p className="text-[12px] leading-[1.7] text-(--color-text-3) line-clamp-3">
                    {space.introduction || '-'}
                  </p>
                </div>
                <div className="mt-3 pt-3 border-t border-(--color-border-1) flex justify-between items-center flex-shrink-0">
                  <span className="text-[12px] text-(--color-text-4)">
                    {t('memory.memoryCount')}: {space.memory_count || 0}
                  </span>
                  <span className="text-[12px] text-(--color-text-4)">
                    {space.created_by || '-'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Spin>

      <OperateModal
        title={editingSpace ? t('memory.editSpace') : t('memory.createSpace')}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onOk={handleSubmit}
        confirmLoading={confirmLoading}
      >
        <DynamicForm form={form} fields={formFields} />
      </OperateModal>
    </div>
  );
};

export default MemoryPage;
