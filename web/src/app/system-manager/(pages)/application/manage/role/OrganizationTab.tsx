import React, { useMemo } from 'react';
import { Button, Input, Spin, Popconfirm, Form, Modal } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from "@/components/permission";
import GroupTreeSelect from '@/components/group-tree-select';

const { Search } = Input;
const { confirm } = Modal;

interface Group {
  id: number;
  name: string;
  parent_id: number;
  description?: string;
}

interface OrganizationTabProps {
  groupTableData: Group[];
  loading: boolean;
  groupCurrentPage: number;
  groupPageSize: number;
  groupTotal: number;
  selectedGroupKeys: React.Key[];
  setSelectedGroupKeys: (keys: React.Key[]) => void;
  deleteLoading: boolean;
  addGroupModalOpen: boolean;
  setAddGroupModalOpen: (open: boolean) => void;
  modalLoading: boolean;
  t: (key: string) => string;
  onSearch: (value: string) => void;
  onTableChange: (page: number, size?: number) => void;
  onAddGroups: (groupIds: number[]) => Promise<void>;
  onDeleteGroup: (record: Group) => Promise<void>;
  onBatchDelete: () => Promise<boolean>;
}

const OrganizationTab: React.FC<OrganizationTabProps> = ({
  groupTableData,
  loading,
  groupCurrentPage,
  groupPageSize,
  groupTotal,
  selectedGroupKeys,
  setSelectedGroupKeys,
  deleteLoading,
  addGroupModalOpen,
  setAddGroupModalOpen,
  modalLoading,
  t,
  onSearch,
  onTableChange,
  onAddGroups,
  onDeleteGroup,
  onBatchDelete
}) => {
  const [addGroupForm] = Form.useForm();

  const columns = useMemo(() => [
    {
      title: t('system.role.organizationName'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, record: Group) => (
        <PermissionWrapper requiredPermissions={['Remove group']}>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => onDeleteGroup(record)}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </PermissionWrapper>
      ),
    },
  ], [t, onDeleteGroup]);

  const openGroupModal = () => {
    addGroupForm.resetFields();
    setAddGroupModalOpen(true);
  };

  const handleAddGroups = async () => {
    try {
      const values = await addGroupForm.validateFields();
      await onAddGroups(values.groups);
      setAddGroupModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    }
  };

  const handleBatchDeleteClick = () => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        await onBatchDelete();
      },
    });
  };

  return (
    <>
      <div className="flex justify-end mb-4">
        <Search
          allowClear
          enterButton
          className='w-60 mr-[8px]'
          onSearch={onSearch}
          placeholder={`${t('common.search')}`}
        />
        <PermissionWrapper requiredPermissions={['Add group']}>
          <Button
            className="mr-[8px]"
            type="primary"
            onClick={openGroupModal}
          >
            +{t('common.add')}
          </Button>
        </PermissionWrapper>
        <PermissionWrapper requiredPermissions={['Remove group']}>
          <Button
            loading={deleteLoading}
            onClick={handleBatchDeleteClick}
            disabled={selectedGroupKeys.length === 0 || deleteLoading}
          >
            {t('system.common.modifydelete')}
          </Button>
        </PermissionWrapper>
      </div>
      <Spin spinning={loading}>
        <CustomTable
          scroll={{ y: 'calc(100vh - 435px)' }}
          rowSelection={{
            selectedRowKeys: selectedGroupKeys,
            onChange: (selectedRowKeys) => setSelectedGroupKeys(selectedRowKeys as React.Key[]),
          }}
          columns={columns}
          dataSource={groupTableData}
          rowKey={(record) => record.id}
          pagination={{
            current: groupCurrentPage,
            pageSize: groupPageSize,
            total: groupTotal,
            onChange: onTableChange,
          }}
        />
      </Spin>
      <OperateModal
        title={t('system.role.addOrganization')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={addGroupModalOpen}
        onOk={handleAddGroups}
        onCancel={() => setAddGroupModalOpen(false)}
      >
        <div className="mb-4 p-3 bg-blue-50 rounded-md border border-blue-200">
          <div className="text-blue-800 text-sm">
            {t('system.role.organizationTip')}
          </div>
        </div>
        <Form form={addGroupForm}>
          <Form.Item
            name="groups"
            label={t('system.role.organizations')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <GroupTreeSelect
              placeholder={`${t('common.select')}${t('system.role.organizations')}`}
              multiple={true}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default OrganizationTab;
