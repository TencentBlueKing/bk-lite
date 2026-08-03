'use client';

import React, {useCallback, useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import Image from 'next/image';
import {Button, Card, Form, Input, message, Modal, Spin, Tag} from 'antd';
import {PlusOutlined} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {useTranslation} from '@/utils/i18n';
import {MemorySpace, useMemoryApi} from '@/app/opspilot/api/memory';
import {useUserInfoContext} from '@/context/userInfo';

const { Search } = Input;

interface MemoryCardProps {
  space: MemorySpace;
  onOpen: (space: MemorySpace) => void;
  onEdit: (space: MemorySpace) => void;
  onDelete: (space: MemorySpace) => void;
}

const MemoryCard: React.FC<MemoryCardProps> = ({space, onOpen, onEdit, onDelete}) => {
  const {t} = useTranslation();
  const isTeamMemory = space.scope === 'team';
  const banner = isTeamMemory ? '/app/banner_bg_2.jpg' : '/app/banner_bg_1.jpg';
  const name = space.name || '-';

  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.currentTarget !== event.target) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(space);
    }
  };

  return (
    <Card
      className="relative min-w-0 cursor-pointer overflow-hidden rounded-xl shadow-md transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-primary) motion-reduce:transition-none motion-reduce:hover:translate-y-0"
      styles={{
        body: {
          padding: 0,
          color: 'var(--color-text-1)',
          border: 'none',
          backgroundColor: 'var(--color-bg)',
        },
      }}
      role="link"
      tabIndex={0}
      aria-label={name}
      onClick={() => onOpen(space)}
      onKeyDown={handleKeyDown}
    >
      <div className="absolute right-2 top-2 z-10">
        <MoreActionsDropdown
          items={[
            {
              key: 'edit',
              label: t('common.edit'),
              permission: 'Edit',
              onClick: () => onEdit(space),
            },
            {
              key: 'delete',
              label: t('common.delete'),
              permission: 'Delete',
              danger: true,
              onClick: () => onDelete(space),
            },
          ]}
          ariaLabel={`${name} ${t('common.more')}`}
          stopPropagation
          buttonClassName="!h-6 !w-6 !border-transparent !bg-transparent !p-0 !text-(--color-text-1) !shadow-none hover:!border-transparent hover:!bg-transparent hover:!text-(--color-text-1) hover:!shadow-none focus-visible:!border-transparent focus-visible:!bg-transparent focus-visible:!text-(--color-text-1) focus-visible:!shadow-none active:!border-transparent active:!bg-transparent active:!text-(--color-text-1) active:!shadow-none"
          iconStyle={{fontSize: '18px'}}
          placement="bottomRight"
        />
      </div>

      <div className="relative h-12.5 w-full">
        <Image
          alt=""
          src={banner}
          fill
          sizes="(min-width: 1536px) 20vw, (min-width: 1024px) 25vw, (min-width: 768px) 33vw, (min-width: 640px) 50vw, 100vw"
          className="object-cover"
        />
      </div>
      <div className="relative p-4">
        <EllipsisWithTooltip
          text={name}
          className="truncate text-sm font-semibold text-(--color-text-1)"
        />
        <p className="mt-3 mb-2 h-12.5 text-xs text-(--color-text-3) line-clamp-3">
          {space.introduction || '-'}
        </p>
        <div className="flex min-w-0 items-end justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1.5">
            <Tag className="font-mini px-0.5 leading-inherit !m-0" color="purple">
              {t('memory.memoryCount')}: {space.memory_count ?? 0}
            </Tag>
            <Tag className="font-mini px-0.5 leading-inherit !m-0" color="blue">
              {isTeamMemory ? t('memory.team') : t('memory.personal')}
            </Tag>
          </div>
          <EllipsisWithTooltip
            text={space.created_by || '-'}
            className="min-w-0 truncate text-right text-xs text-(--color-text-4)"
          />
        </div>
      </div>
    </Card>
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
      <div className="mb-4 flex justify-end">
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
          <Search
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            onSearch={(value) => setSearchTerm(value)}
            onChange={(e) => !e.target.value && setSearchTerm('')}
            className="w-full sm:w-60"
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} className="w-full sm:w-auto">
              {t('memory.createMemory')}
            </Button>
          </PermissionWrapper>
        </div>
      </div>

      <Spin spinning={loading}>
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
