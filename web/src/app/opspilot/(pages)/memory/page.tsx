'use client';

import React, {useCallback, useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {Button, Form, Input, Menu, message, Modal} from 'antd';
import {PlusOutlined} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import {useTranslation} from '@/utils/i18n';
import {MemorySpace, useMemoryApi} from '@/app/opspilot/api/memory';
import {useUserInfoContext} from '@/context/userInfo';
import UnifiedOpsCard from '@/app/opspilot/components/unified-ops-card';
import OpsPilotListPageHeader from '@/app/opspilot/components/opspilot-list-page-header';
import OpsPilotCardGridSkeleton from '@/app/opspilot/components/opspilot-card-grid-skeleton';
import { formatRelativeTime, pickEntityTimestamp } from '@/app/opspilot/utils/relativeTime';
import { pickStableIcon } from '@/app/opspilot/utils/pickStableIcon';

const { Search } = Input;

const MEMORY_ICON_POOL = ['jiyi1', 'icon_chaojijiyi'];

interface MemoryCardProps {
  space: MemorySpace;
  onOpen: (space: MemorySpace) => void;
  onEdit: (space: MemorySpace) => void;
  onDelete: (space: MemorySpace) => void;
}

const MemoryCard: React.FC<MemoryCardProps> = ({space, onOpen, onEdit, onDelete}) => {
  const {t} = useTranslation();
  const isTeamMemory = space.scope === 'team';
  const name = space.name || '-';

  const menu = (
    <Menu>
      <Menu.Item key={`edit-${space.id}`}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <span className="block" onClick={() => onEdit(space)}>
            {t('common.edit')}
          </span>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key={`delete-${space.id}`} danger>
        <PermissionWrapper requiredPermissions={['Delete']}>
          <span
            className="block"
            onClick={() => {
              Modal.confirm({
                title: t('memory.deleteConfirm'),
                content: t('memory.deleteConfirmContent', undefined, { name }),
                onOk: () => onDelete(space),
              });
            }}
          >
            {t('common.delete')}
          </span>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  return (
    <UnifiedOpsCard
      name={name}
      description={space.introduction || '-'}
      icon={pickStableIcon(space.id, MEMORY_ICON_POOL, name)}
      updatedAt={formatRelativeTime(pickEntityTimestamp(space), t) || undefined}
      meta={[`${t('memory.memoryCount')}: ${space.memory_count ?? 0}`]}
      footer="entity"
      owner={space.created_by || '--'}
      team={isTeamMemory ? t('memory.team') : t('memory.personal')}
      menuOverlay={menu}
      onClick={() => onOpen(space)}
    />
  );
};
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

  const handleDelete = async (space: MemorySpace) => {
    try {
      await deleteMemorySpace(space.id);
      message.success(t('common.delSuccess'));
      loadSpaces();
    } catch {
      message.error(t('common.delFailed'));
    }
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

  const handleOpen = (space: MemorySpace) => {
    router.push(`/opspilot/memory/detail/config?id=${space.id}`);
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
      <OpsPilotListPageHeader
        title={t('memory.pageTitle')}
        description={t('memory.pageDescription')}
        actions={
          <>
            <Search
              allowClear
              enterButton
              placeholder={`${t('common.search')}...`}
              onSearch={(value) => setSearchTerm(value)}
              onChange={(e) => !e.target.value && setSearchTerm('')}
              className="w-60"
            />
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          </>
        }
      />

      {loading ? (
        <OpsPilotCardGridSkeleton />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
          {filteredSpaces.map((space) => (
            <MemoryCard
              key={space.id}
              space={space}
              onOpen={handleOpen}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

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
