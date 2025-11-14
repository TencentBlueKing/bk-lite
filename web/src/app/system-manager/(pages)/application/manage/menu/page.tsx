'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { message, Button, Input, Tag, Spin, Dropdown, Form, Modal } from 'antd';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useRoleApi } from '@/app/system-manager/api/application';
import { CustomMenu, CustomMenuListParams } from '@/app/system-manager/types/menu';
import { useMenus } from '@/context/menus';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import CustomTable from '@/components/custom-table';
import styles from '@/app/system-manager/styles/common.module.scss';

const { Search } = Input;

const CustomMenuPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const clientId = searchParams.get('clientId') || '';
  const { configMenus } = useMenus();
  
  const {
    getCustomMenus,
    addCustomMenu,
    deleteCustomMenu,
    toggleCustomMenuStatus,
    copyCustomMenu
  } = useRoleApi();

  // State management
  const [dataList, setDataList] = useState<CustomMenu[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [menuModalVisible, setMenuModalVisible] = useState(false);
  const [menuForm] = Form.useForm();
  const [modalLoading, setModalLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<{ [key: string]: boolean }>({});

  // Load menu list
  const loadMenus = useCallback(
    async (page = 1, search = '') => {
      if (!clientId) {
        return;
      }

      setLoading(true);
      try {
        const params: CustomMenuListParams = {
          app: clientId,
          page,
          page_size: pagination.pageSize,
        };

        if (search) {
          params.search = search;
        }

        const response = await getCustomMenus({ params });
        setDataList(response.items || []);
        setPagination(prev => ({
          ...prev,
          current: page,
          total: response.count || 0,
        }));
      } catch (error) {
        console.error('Failed to load custom menus:', error);
      } finally {
        setLoading(false);
      }
    },
    [clientId, pagination.pageSize]
  );

  // Initial load
  useEffect(() => {
    if (clientId) {
      loadMenus(1);
    }
  }, [clientId]);

  // Search handler
  const handleSearch = (value: string) => {
    setSearchTerm(value);
    loadMenus(1, value);
  };

  // Toggle menu status
  const handleToggleStatus = async (record: CustomMenu) => {
    const loadingKey = `toggle-${record.id}`;
    if (actionLoading[loadingKey]) return;
    
    setActionLoading(prev => ({ ...prev, [loadingKey]: true }));
    try {
      await toggleCustomMenuStatus({
        id: record.id,
        is_enabled: !record.is_enabled,
      });
      message.success(t('common.success'));
      loadMenus(pagination.current, searchTerm);
    } catch (error) {
      message.error(t('common.failed'));
      console.error('Failed to toggle menu status:', error);
    } finally {
      setActionLoading(prev => ({ ...prev, [loadingKey]: false }));
    }
  };

  // Copy menu
  const handleCopyMenu = async (record: CustomMenu) => {
    const loadingKey = `copy-${record.id}`;
    if (actionLoading[loadingKey]) return;
    
    setActionLoading(prev => ({ ...prev, [loadingKey]: true }));
    try {
      const copyData: any = {
        id: record.id,
        app: clientId,
        display_name: `${record.display_name}_copy`,
        description: record.description,
      };

      // 如果是内置菜单，添加 menus 字段（从源菜单树获取）
      if (record.is_build_in) {
        const appMenus = configMenus.filter(menu => {
          if (!menu.url || !clientId) return false;
          const urlParts = menu.url.split('/').filter(Boolean);
          const appName = urlParts[0];
          return appName === clientId;
        });

        const menus = appMenus
          .filter(menu => menu.url && menu.children && menu.children.length > 0)
          .map(menu => ({
            name: menu.name,
            title: menu.title,
            url: menu.url,
            icon: menu.icon,
            children: menu.children?.map(child => ({
              name: child.name,
              title: child.title,
              url: child.url,
              icon: child.icon,
            })) || []
          }));

        copyData.menus = menus;
      }

      await copyCustomMenu(copyData);
      message.success(t('common.success'));
      loadMenus(pagination.current, searchTerm);
    } catch (error) {
      message.error(t('common.failed'));
      console.error('Failed to copy menu:', error);
    } finally {
      setActionLoading(prev => ({ ...prev, [loadingKey]: false }));
    }
  };

  // Delete menu
  const handleDeleteMenu = async (record: CustomMenu) => {
    const loadingKey = `delete-${record.id}`;
    if (actionLoading[loadingKey]) return;
    
    setActionLoading(prev => ({ ...prev, [loadingKey]: true }));
    try {
      await deleteCustomMenu({ id: record.id });
      message.success(t('common.success'));
      loadMenus(pagination.current, searchTerm);
    } catch (error) {
      message.error(t('common.failed'));
      console.error('Failed to delete menu:', error);
    } finally {
      setActionLoading(prev => ({ ...prev, [loadingKey]: false }));
    }
  };

  // Add menu modal submit
  const handleAddMenuSubmit = async (values: { display_name: string }) => {
    setModalLoading(true);
    try {
      await addCustomMenu({
        display_name: values.display_name,
        app: clientId,
      });
      message.success(t('common.addSuccess'));
      menuForm.resetFields();
      setMenuModalVisible(false);
      loadMenus(pagination.current, searchTerm);
    } catch (error) {
      message.error(t('common.addFail'));
      console.error('Failed to add menu:', error);
    } finally {
      setModalLoading(false);
    }
  };

  const columns = [
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
      render: (_: any, record: CustomMenu) => {
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
              router.push(`/system-manager/application/manage/menu/config?clientId=${clientId}&menuId=${record.id}`);
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

        // Filter operations by permission (simplified - you can enhance this with actual permission checks)
        const visibleOps = operations;

        // Show first 3 as buttons, rest in dropdown
        const directOps = visibleOps.slice(0, 3);
        const dropdownOps = visibleOps.slice(3);

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
                      const op = dropdownOps.find(o => o.key === key);
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
  ];

  // Filtered data based on search
  const filteredData = useMemo(() => {
    return dataList;
  }, [dataList]);

  // Get form fields for modal
  const getFormFields = () => {
    return [
      {
        name: 'display_name',
        type: 'input',
        label: t('system.menu.name'),
        placeholder: `${t('common.inputMsg')}${t('system.menu.name')}`,
        rules: [
          { required: true, message: `${t('common.inputMsg')}${t('system.menu.name')}` },
          { max: 100, message: 'Max length 100' }
        ],
      },
    ];
  };

  return (
    <div className="w-full bg-[var(--color-bg)] rounded-md h-full p-4">
      {/* Top Bar: Search and Add Button */}
      <div className="flex justify-end gap-2 mb-4">
        <Search
          allowClear
          enterButton
          className='w-60'
          onSearch={handleSearch}
          placeholder={t('system.menu.search')}
        />
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              menuForm.resetFields();
              setMenuModalVisible(true);
            }}
          >
            {t('common.add')}
          </Button>
        </PermissionWrapper>
      </div>

      {/* Add Menu Modal */}
      <OperateModal
        title={t('common.add')}
        open={menuModalVisible}
        onOk={() => {
          menuForm.validateFields().then(() => {
            const values = menuForm.getFieldsValue(true);
            handleAddMenuSubmit(values);
          }).catch(() => {
            // Validation failed
          });
        }}
        onCancel={() => {
          setMenuModalVisible(false);
          menuForm.resetFields();
        }}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
      >
        <DynamicForm
          form={menuForm}
          fields={getFormFields()}
        />
      </OperateModal>

      {/* Table */}
      <Spin spinning={loading}>
        <CustomTable
          columns={columns}
          dataSource={filteredData}
          rowKey="id"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (page: number) => loadMenus(page, searchTerm),
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50'],
            onShowSizeChange: (_: number, size: number) => {
              setPagination(prev => ({ ...prev, pageSize: size }));
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
