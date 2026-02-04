'use client';

import React, { useEffect, useMemo, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Button, Input, Tag, Spin, Dropdown, Form, Modal } from 'antd';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { CustomMenu } from '@/app/system-manager/types/menu';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import CustomTable from '@/components/custom-table';
import styles from '@/app/system-manager/styles/common.module.scss';
import {
  useCustomMenuList,
  useCustomMenuActions,
  useCustomMenuModal,
} from '@/app/system-manager/hooks/useCustomMenuPage';

const { Search } = Input;

const CustomMenuPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const clientId = searchParams.get('clientId') || '';
  const [menuForm] = Form.useForm();

  const {
    dataList,
    loading,
    pagination,
    searchTerm,
    setPagination,
    loadMenus,
    handleSearch,
  } = useCustomMenuList(clientId);

  const refreshList = useCallback(() => {
    loadMenus(pagination.current, searchTerm);
  }, [loadMenus, pagination.current, searchTerm]);

  const { actionLoading, handleToggleStatus, handleCopyMenu, handleDeleteMenu } =
    useCustomMenuActions(clientId, refreshList);

  const { menuModalVisible, modalLoading, openModal, closeModal, handleAddMenuSubmit } =
    useCustomMenuModal(clientId, refreshList, () => menuForm.resetFields());

  useEffect(() => {
    if (clientId) {
      loadMenus(1);
    }
  }, [clientId]);

  const getFormFields = useMemo(
    () => [
      {
        name: 'display_name',
        type: 'input',
        label: t('system.menu.name'),
        placeholder: `${t('common.inputMsg')}${t('system.menu.name')}`,
        rules: [
          { required: true, message: `${t('common.inputMsg')}${t('system.menu.name')}` },
          { max: 100, message: 'Max length 100' },
        ],
      },
    ],
    [t]
  );

  const columns = useMemo(
    () => [
      {
        title: t('system.menu.name'),
        dataIndex: 'display_name',
        key: 'display_name',
        render: (text: string) => <span className={styles.textEllipsis}>{text}</span>,
      },
      {
        title: t('system.menu.updatedBy'),
        dataIndex: 'updated_by',
        key: 'updated_by',
        render: (text: string) => <span className={styles.textEllipsis}>{text}</span>,
      },
      {
        title: t('system.menu.updatedAt'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        render: (text: string) => {
          if (!text) return '-';
          try {
            const date = new Date(text);
            return date.toLocaleString('zh-CN');
          } catch {
            return text;
          }
        },
      },
      {
        title: t('system.menu.enabled'),
        dataIndex: 'is_enabled',
        key: 'is_enabled',
        render: (enabled: boolean) => (
          <Tag color={enabled ? 'green' : 'red'}>
            {enabled ? t('system.menu.enable') : t('system.menu.disable')}
          </Tag>
        ),
      },
      {
        title: t('common.actions'),
        key: 'actions',
        render: (_: unknown, record: CustomMenu) => {
          const operations = [
            {
              key: 'toggle',
              label: record.is_enabled ? t('system.menu.disable') : t('system.menu.enable'),
              onClick: () => handleToggleStatus(record),
              permission: 'Edit',
            },
            {
              key: 'copy',
              label: t('system.menu.copy'),
              onClick: () => handleCopyMenu(record),
              permission: 'Edit',
            },
            {
              key: 'edit',
              label: t('common.edit'),
              onClick: () => {
                router.push(
                  `/system-manager/application/manage/menu/config?clientId=${clientId}&menuId=${record.id}`
                );
              },
              permission: 'Edit',
              disabled: record.is_build_in,
            },
            {
              key: 'delete',
              label: t('system.menu.delete'),
              onClick: () => handleDeleteMenu(record),
              permission: 'Delete',
              danger: true,
              disabled: record.is_build_in,
            },
          ];

          const directOps = operations.slice(0, 3);
          const dropdownOps = operations.slice(3);

          return (
            <div className="flex space-x-1">
              {directOps.map((op) => (
                <PermissionWrapper key={op.key} requiredPermissions={[op.permission]}>
                  <Button
                    type="link"
                    onClick={op.onClick}
                    loading={actionLoading[`${op.key}-${record.id}`]}
                    disabled={op.disabled}
                  >
                    {op.label}
                  </Button>
                </PermissionWrapper>
              ))}

              {dropdownOps.length > 0 && (
                <PermissionWrapper requiredPermissions={['Delete']}>
                  <Dropdown
                    menu={{
                      items: dropdownOps.map((op) => ({
                        key: op.key,
                        label: op.label,
                        danger: op.danger,
                        disabled: op.disabled,
                      })),
                      onClick: ({ key }) => {
                        const op = dropdownOps.find((o) => o.key === key);
                        if (op?.key === 'delete') {
                          Modal.confirm({
                            title: t('common.delConfirm'),
                            okText: t('common.confirm'),
                            cancelText: t('common.cancel'),
                            onOk: () => op.onClick(),
                          });
                        } else {
                          op?.onClick();
                        }
                      },
                    }}
                  >
                    <Button type="link" icon={<MoreOutlined />} />
                  </Dropdown>
                </PermissionWrapper>
              )}
            </div>
          );
        },
      },
    ],
    [t, clientId, router, actionLoading, handleToggleStatus, handleCopyMenu, handleDeleteMenu]
  );

  return (
    <div className="w-full bg-[var(--color-bg)] rounded-md h-full p-4">
      <div className="flex justify-end gap-2 mb-4">
        <Search
          allowClear
          enterButton
          className="w-60"
          onSearch={handleSearch}
          placeholder={t('system.menu.search')}
        />
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openModal}>
            {t('common.add')}
          </Button>
        </PermissionWrapper>
      </div>

      <OperateModal
        title={t('common.add')}
        open={menuModalVisible}
        onOk={() => {
          menuForm
            .validateFields()
            .then(() => {
              const values = menuForm.getFieldsValue(true);
              handleAddMenuSubmit(values);
            })
            .catch(() => {});
        }}
        onCancel={closeModal}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
      >
        <DynamicForm form={menuForm} fields={getFormFields} />
      </OperateModal>

      <Spin spinning={loading}>
        <CustomTable
          columns={columns}
          dataSource={dataList}
          rowKey="id"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (page: number) => loadMenus(page, searchTerm),
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50'],
            onShowSizeChange: (_: number, size: number) => {
              setPagination((prev) => ({ ...prev, pageSize: size }));
              loadMenus(1, searchTerm);
            },
          }}
          scroll={{ x: 1200, y: 'calc(100vh - 365px)' }}
          locale={{
            emptyText: t('system.menu.noData'),
          }}
        />
      </Spin>
    </div>
  );
};

export default CustomMenuPage;
