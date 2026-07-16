import React from 'react';
import { Button } from 'antd';
import ManagementTableShell from '@/components/management-table-shell';
import OperateFormModal from '@/components/operate-form-modal';
import PermissionWrapper from '@/components/permission';

export interface SystemManagerRoleAssignmentTabShellProps {
  loading: boolean;
  deleteLoading?: boolean;
  selectedKeys: React.Key[];
  addPermission: string;
  removePermission: string;
  searchPlaceholder: string;
  addLabel: React.ReactNode;
  batchDeleteLabel: React.ReactNode;
  modalTitle: React.ReactNode;
  confirmText?: React.ReactNode;
  cancelText?: React.ReactNode;
  modalOpen: boolean;
  modalLoading?: boolean;
  tableScrollY?: string;
  columns: unknown[];
  dataSource: unknown[];
  rowKey: (record: any) => React.Key;
  pagination: {
    current?: number;
    pageSize?: number;
    total?: number;
    onChange: (page: number, size?: number) => void;
  };
  onSearch: (value: string) => void;
  onOpenAddModal: () => void;
  onBatchDelete: () => void;
  onSelectionChange: (keys: React.Key[]) => void;
  onConfirmModal: () => void;
  onCancelModal: () => void;
  modalContent: React.ReactNode;
}

const SystemManagerRoleAssignmentTabShell: React.FC<SystemManagerRoleAssignmentTabShellProps> = ({
  loading,
  deleteLoading = false,
  selectedKeys,
  addPermission,
  removePermission,
  searchPlaceholder,
  addLabel,
  batchDeleteLabel,
  modalTitle,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  modalOpen,
  modalLoading = false,
  tableScrollY = 'calc(100vh - 435px)',
  columns,
  dataSource,
  rowKey,
  pagination,
  onSearch,
  onOpenAddModal,
  onBatchDelete,
  onSelectionChange,
  onConfirmModal,
  onCancelModal,
  modalContent,
}) => {
  const isBatchDisabled = selectedKeys.length === 0 || deleteLoading;

  return (
    <>
      <ManagementTableShell
        loading={loading}
        searchProps={{
          onSearch,
          placeholder: searchPlaceholder,
        }}
        actions={(
          <>
            <PermissionWrapper requiredPermissions={[addPermission]}>
              <Button
                type="primary"
                onClick={onOpenAddModal}
              >
                {addLabel}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={[removePermission]}>
              <Button
                loading={deleteLoading}
                onClick={onBatchDelete}
                disabled={isBatchDisabled}
              >
                {batchDeleteLabel}
              </Button>
            </PermissionWrapper>
          </>
        )}
        columns={columns}
        dataSource={dataSource}
        rowKey={rowKey}
        pagination={pagination}
        scroll={{ y: tableScrollY }}
        rowSelection={{
          selectedRowKeys: selectedKeys,
          onChange: (keys) => onSelectionChange(keys as React.Key[]),
        }}
        panelClassName=""
        modal={(
          <OperateFormModal
            title={modalTitle}
            closable={false}
            open={modalOpen}
            confirmText={confirmText}
            cancelText={cancelText}
            confirmLoading={modalLoading}
            cancelDisabled={modalLoading}
            onConfirm={onConfirmModal}
            onCancel={onCancelModal}
          >
            {modalContent}
          </OperateFormModal>
        )}
      />
    </>
  );
};

export default SystemManagerRoleAssignmentTabShell;
