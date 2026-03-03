"use client";
import React, { useMemo } from 'react';
import { Button, Input, Form, Spin, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import PermissionWrapper from "@/components/permission";
import PermissionRule from '@/app/system-manager/components/application/permissionRule';
import type { DataItem } from '@/app/system-manager/types/permission';
import {
  useDataList,
  useModuleConfig,
  useDataModal
} from '@/app/system-manager/hooks/useDataManagement';

const { Search } = Input;

const DataManagement: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const clientId = searchParams ? searchParams.get('clientId') : null;

  const [dataForm] = Form.useForm();

  const {
    dataList,
    loading,
    currentPage,
    pageSize,
    total,
    fetchDataList,
    handleTableChange,
    handleSearch,
    handleDelete
  } = useDataList({ clientId });

  const {
    supportedModules,
    moduleConfigs,
    fetchAppModules
  } = useModuleConfig({ clientId });

  const {
    dataModalOpen,
    isEditing,
    modalLoading,
    currentGroupId,
    showDataModal,
    handleDataModalSubmit,
    handleModalCancel,
    handleGroupChange
  } = useDataModal({
    clientId,
    supportedModules,
    moduleConfigs,
    fetchAppModules,
    fetchDataList,
    dataForm
  });

  const columns = useMemo(() => [
    {
      title: t('system.data.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('system.data.description'),
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: t('system.data.group'),
      dataIndex: 'group_name',
      key: 'group_name',
      render: (group_name: string) => group_name || '-'
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, record: DataItem) => (
        <div className="flex space-x-2">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              onClick={() => showDataModal(record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('common.delConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDelete(record, id)}
            >
              <Button type="link">
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </div>
      ),
    },
  ], [t, showDataModal, handleDelete, id]);

  const formFields = useMemo(() => [
    {
      name: 'name',
      type: 'input',
      label: t('system.data.name'),
      placeholder: `${t('common.inputMsg')}${t('system.data.name')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.data.name')}` }],
    },
    {
      name: 'description',
      type: 'textarea',
      label: t('system.data.description'),
      placeholder: `${t('common.inputMsg')}${t('system.data.description')}`,
      rows: 4,
    },
    {
      name: 'groupId',
      type: 'custom',
      label: t('system.data.group'),
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.data.group')}` }],
      component: (
        <GroupTreeSelect
          multiple={false}
          placeholder={`${t('common.inputMsg')}${t('system.data.group')}`}
          onChange={handleGroupChange}
        />
      )
    },
    {
      name: 'permissionRule',
      type: 'custom',
      label: t('system.permission.dataPermissionRule'),
      component: (
        <PermissionRule
          key={`permission-rule-${currentGroupId}`}
          modules={supportedModules}
          formGroupId={currentGroupId}
          onChange={(newVal: Record<string, unknown>) => {
            dataForm.setFieldsValue({ permissionRule: newVal });
          }}
        />
      ),
    },
  ], [t, handleGroupChange, currentGroupId, supportedModules, dataForm]);

  return (
    <div className="w-full bg-[var(--color-bg)] rounded-md h-full p-4">
      <div className="flex justify-end mb-4">
        <Search
          allowClear
          enterButton
          className='w-60 mr-[8px]'
          onSearch={handleSearch}
          placeholder={`${t('common.search')}`}
        />
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button
            type="primary"
            onClick={() => showDataModal()}
            icon={<PlusOutlined />}
          >
            {t('common.add')}
          </Button>
        </PermissionWrapper>
      </div>
      <Spin spinning={loading}>
        <CustomTable
          scroll={{ y: 'calc(100vh - 365px)' }}
          columns={columns}
          dataSource={dataList}
          rowKey={(record) => record.id}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: total,
            onChange: handleTableChange,
          }}
        />
      </Spin>
      <OperateModal
        width={800}
        title={isEditing ? t('common.edit') : t('common.add')}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={dataModalOpen}
        onOk={handleDataModalSubmit}
        onCancel={handleModalCancel}
      >
        <DynamicForm
          key={`form-${currentGroupId}-${dataModalOpen ? 'open' : 'closed'}`}
          form={dataForm}
          fields={formFields}
          initialValues={{ permissionRule: dataForm.getFieldValue('permissionRule') }}
        />
      </OperateModal>
    </div>
  );
};

export default DataManagement;
