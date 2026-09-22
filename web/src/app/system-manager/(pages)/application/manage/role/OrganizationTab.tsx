import React, { useMemo } from 'react';
import { Button, Popconfirm, Form, Modal } from 'antd';
import CustomTable from '@/components/custom-table';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from "@/components/permission";
import GroupTreeSelect from '@/components/group-tree-select';
import SearchActionBar from '@/components/search-action-bar';

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
    <div className="flex h-full min-h-0 flex-col">
      <SearchActionBar
        searchProps={{
          placeholder: `${t('common.search')}`,
          onSearch,
        }}
        actions={(
          <>
            <PermissionWrapper requiredPermissions={['Remove group']}>
              <Button
                loading={deleteLoading}
                onClick={handleBatchDeleteClick}
                disabled={selectedGroupKeys.length === 0 || deleteLoading}
              >
                {t('system.common.modifydelete')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Add group']}>
              <Button
                type="primary"
                onClick={openGroupModal}
              >
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          </>
        )}
      />
      <SystemManagerFillTable>
        <CustomTable
          loading={loading}
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
            showSizeChanger: true,
            onChange: onTableChange,
          }}
        />
      </SystemManagerFillTable>
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
        <div className="mb-4 rounded-md border border-[var(--color-primary)]/20 bg-[color-mix(in_srgb,var(--color-primary)_8%,var(--color-bg))] p-3">
          <div className="text-sm text-[var(--color-text-1)]">
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
    </div>
  );
};

export default OrganizationTab;
