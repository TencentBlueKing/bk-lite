"use client";
import React, { useState, useEffect } from 'react';
import { Button, Input, Form, message, Spin, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { CLIENT_MODULES_MAP } from '@/app/system-manager/constants/application'
import { useRoleApi } from '@/app/system-manager/api/application';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import PermissionRule from '@/app/system-manager/components/application/permissionRule';
import {
  DataItem,
  PermissionRuleItem,
  PermissionConfig
} from '@/app/system-manager/types/permission';

const { Search } = Input;

const convertPermissionsForApi = (
  moduleConfig: any,
  isProvider: boolean = false,
  subModule?: string
): PermissionRuleItem[] => {
  const permissionArray: PermissionRuleItem[] = [];
  const config = isProvider && subModule ? moduleConfig[subModule] : moduleConfig;

  if (!config) return permissionArray;

  if (config.type === 'all') {
    const permissions: string[] = [];

    if (config.allPermissions?.view) {
      permissions.push('View');

      if (config.allPermissions?.operate) {
        permissions.push('Operate');
      }
    }

    if (permissions.length > 0) {
      permissionArray.push({
        id: '0',
        name: 'All',
        permission: permissions
      });
    }
  }

  if (config.specificData && config.specificData.length > 0) {
    config.specificData.forEach((item: any) => {
      const permissions: string[] = [];

      if (item.view) {
        permissions.push('View');

        if (item.operate) {
          permissions.push('Operate');
        }
      }

      if (permissions.length > 0) {
        permissionArray.push({
          id: item.id,
          name: item.name,
          permission: permissions
        });
      }
    });
  }

  return permissionArray;
};

const convertApiDataToFormData = (
  items: PermissionRuleItem[]
): PermissionConfig => {
  const hasWildcard = items.some(item => item.id === '0');

  let wildcardItem;
  if (hasWildcard) {
    wildcardItem = items.find(item => item.id === '0');
  }

  const wildcardPermissions = wildcardItem?.permission || [];
  const hasView = wildcardPermissions.includes("View");
  const hasOperate = wildcardPermissions.includes("Operate");

  return {
    type: hasWildcard ? 'all' : 'specific',
    allPermissions: hasWildcard ? {
      view: hasView,
      operate: hasOperate
    } : { view: true, operate: true },
    specificData: items
      .filter(item => item.id !== '0')
      .map(item => {
        const hasItemView = item.permission.includes("View");
        const hasItemOperate = item.permission.includes("Operate");
        return {
          id: item.id,
          name: item.name,
          view: hasItemView,
          operate: hasItemOperate
        };
      })
  };
};

const createDefaultPermissionRule = (modules: string[]): Record<string, any> => {
  const defaultPermissionRule: Record<string, any> = {};

  modules.forEach(module => {
    if (module === 'provider') {
      defaultPermissionRule.provider = {
        llm_model: { type: 'all', allPermissions: { view: true, operate: true }, specificData: [] },
        embed_model: { type: 'all', allPermissions: { view: true, operate: true }, specificData: [] },
        rerank_model: { type: 'all', allPermissions: { view: true, operate: true }, specificData: [] },
        ocr_model: { type: 'all', allPermissions: { view: true, operate: true }, specificData: [] }
      };
    } else {
      defaultPermissionRule[module] = {
        type: 'all',
        allPermissions: { view: true, operate: true },
        specificData: []
      };
    }
  });

  return defaultPermissionRule;
};

const DataManagement: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const clientId = searchParams ? searchParams.get('clientId') : null;
  const { groups } = useUserInfoContext();

  const [dataForm] = Form.useForm();
  const [dataList, setDataList] = useState<DataItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [dataModalOpen, setDataModalOpen] = useState(false);
  const [selectedData, setSelectedData] = useState<DataItem | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [currentGroupId, setCurrentGroupId] = useState<string>("");
  const [selectChanged, setSelectChanged] = useState(false);

  const {
    getGroupDataRule,
    deleteGroupDataRule,
    addGroupDataRule,
    updateGroupDataRule
  } = useRoleApi();

  useEffect(() => {
    fetchDataList();
  }, [currentPage, pageSize]);

  useEffect(() => {
    if (currentGroupId && selectChanged) {
      const currentPermissions = dataForm.getFieldValue('permissionRule');
      dataForm.setFieldsValue({
        permissionRule: {
          ...currentPermissions,
          _forceUpdate: Date.now()
        }
      });
      setSelectChanged(false);
    }
  }, [currentGroupId, selectChanged]);

  const fetchDataList = async (search?: string) => {
    if (!id) return;

    setLoading(true);
    try {
      const params: any = { client_id: id, page: currentPage, page_size: pageSize };
      if (search) {
        params.search = search;
      }

      const data = await getGroupDataRule({ params });
      setDataList(data.items);
      setTotal(data.count);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (page: number, size?: number) => {
    setCurrentPage(page);
    if (size) {
      setPageSize(size);
    }
  };

  const showDataModal = (data: DataItem | null = null) => {
    setIsEditing(!!data);
    setSelectedData(data);

    setModalLoading(true);

    dataForm.resetFields();

    const supportedModules = clientId && Object.prototype.hasOwnProperty.call(CLIENT_MODULES_MAP, clientId)
      ? CLIENT_MODULES_MAP[clientId as keyof typeof CLIENT_MODULES_MAP]
      : [];
    const defaultPermissionRule = createDefaultPermissionRule(supportedModules);

    if (data) {
      const formattedPermissionRule: Record<string, any> = {};
      if (data.rules) {
        Object.keys(data.rules).forEach(moduleKey => {
          if (moduleKey === 'provider') {
            formattedPermissionRule.provider = {};
            Object.keys(data.rules?.provider || {}).forEach(subModule => {
              const items = data.rules?.provider?.[subModule] || [];
              formattedPermissionRule.provider[subModule] = convertApiDataToFormData(items);
            });
          } else {
            const items = data.rules[moduleKey] || [];
            formattedPermissionRule[moduleKey] = convertApiDataToFormData(items);
          }
        });
      }

      const mergedPermissionRule = { ...defaultPermissionRule, ...formattedPermissionRule };

      dataForm.setFieldsValue({
        name: data.name,
        description: data.description,
        groupId: data.group_id,
        permissionRule: mergedPermissionRule
      });

      setCurrentGroupId(data.group_id);
    } else {
      const initialGroupId = groups.length > 0 ? groups[0].id : undefined;
      dataForm.setFieldsValue({
        permissionRule: defaultPermissionRule,
        groupId: initialGroupId
      });
      setCurrentGroupId(initialGroupId || "");
    }

    setTimeout(() => {
      setDataModalOpen(true);
      setModalLoading(false);
    }, 0);
  };

  const handleDataModalSubmit = async () => {
    try {
      setModalLoading(true);
      await dataForm.validateFields();
      const values = dataForm.getFieldsValue(true);

      if (!values.permissionRule) {
        values.permissionRule = {};
      }

      const transformedRules: Record<string, any> = {};
      const supportedModules = clientId && Object.keys(CLIENT_MODULES_MAP).includes(clientId)
        ? CLIENT_MODULES_MAP[clientId as keyof typeof CLIENT_MODULES_MAP]
        : [];

      supportedModules.forEach(moduleKey => {
        if (moduleKey === 'provider') {
          const providerConfig = values.permissionRule.provider || {};
          const providerRules: Record<string, PermissionRuleItem[]> = {};

          Object.keys(providerConfig).forEach(subModule => {
            if (subModule === '__type') return;
            const permissionArray = convertPermissionsForApi(providerConfig, true, subModule);

            if (permissionArray.length > 0) {
              providerRules[subModule] = permissionArray;
            }
          });

          if (Object.keys(providerRules).length > 0) {
            transformedRules.provider = providerRules;
          }
        } else {
          const moduleConfig = values.permissionRule[moduleKey];
          if (!moduleConfig) return;
          const permissionArray = convertPermissionsForApi(moduleConfig);

          if (permissionArray.length > 0) {
            transformedRules[moduleKey] = permissionArray;
          }
        }
      });

      const requestData = {
        name: values.name,
        description: values.description || "",
        group_id: values.groupId,
        group_name: groups.find(g => g.id === values.groupId)?.name || "",
        app: clientId,
        rules: transformedRules
      };

      if (isEditing && selectedData) {
        await updateGroupDataRule({
          id: selectedData.id,
          ...requestData
        });
        message.success(t('common.updateSuccess'));
      } else {
        await addGroupDataRule(requestData);
        message.success(t('common.addSuccess'));
      }

      fetchDataList();
      setDataModalOpen(false);
      dataForm.resetFields();
    } catch (error) {
      console.error('Form submission failed:', error);
      message.error(isEditing ? t('common.updateFail') : t('common.addFail'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = async (data: DataItem) => {
    if (!id) return;

    try {
      await deleteGroupDataRule({
        id: data.id,
        client_id: id
      });
      message.success(t('common.delSuccess'));
      fetchDataList();
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  };

  const handleSearch = (value: string) => {
    setCurrentPage(1);
    fetchDataList(value);
  };

  const getFormFields = () => {
    return [
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
        type: 'select',
        label: t('system.data.group'),
        placeholder: `${t('common.inputMsg')}${t('system.data.group')}`,
        rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.data.group')}` }],
        options: groups.map(group => ({ value: group.id, label: group.name })),
        onChange: (value: string) => {
          setCurrentGroupId(value);
          setSelectChanged(true);

          const currentPermissions = dataForm.getFieldValue('permissionRule');
          if (currentPermissions) {
            dataForm.setFieldsValue({
              permissionRule: {
                ...currentPermissions,
                _timestamp: Date.now()
              }
            });
          }
        }
      },
      {
        name: 'permissionRule',
        type: 'custom',
        label: t('system.permission.dataPermissionRule'),
        component: (
          <PermissionRule
            key={`permission-rule-${currentGroupId}`}
            modules={clientId && clientId in CLIENT_MODULES_MAP ? CLIENT_MODULES_MAP[clientId as keyof typeof CLIENT_MODULES_MAP] : []}
            formGroupId={currentGroupId}
            onChange={(newVal: any) => {
              dataForm.setFieldsValue({ permissionRule: newVal });
            }}
          />
        ),
      },
    ];
  };

  const columns = [
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
      render: (_: any, record: DataItem) => (
        <div className="flex space-x-2">
          <Button
            type="link"
            onClick={() => showDataModal(record)}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => handleDelete(record)}
          >
            <Button type="link">
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ];
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
        <Button
          type="primary"
          onClick={() => showDataModal()}
          icon={<PlusOutlined />}
        >
          {t('common.add')}
        </Button>
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
        title={isEditing ? t('common.edit') : t('common.add')}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={dataModalOpen}
        onOk={handleDataModalSubmit}
        onCancel={() => {
          setDataModalOpen(false);
          dataForm.resetFields();
          setCurrentGroupId("");
        }}
      >
        <DynamicForm
          key={`form-${currentGroupId}-${dataModalOpen ? 'open' : 'closed'}`}
          form={dataForm}
          fields={getFormFields()}
          initialValues={{ permissionRule: dataForm.getFieldValue('permissionRule') }}
        />
      </OperateModal>
    </div>
  );
};

export default DataManagement;
