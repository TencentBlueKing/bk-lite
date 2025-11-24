"use client";
import React, { useState, useEffect, useCallback } from 'react';
import { Button, Input, Form, message, Spin, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { buildModulesMap } from '@/app/system-manager/constants/application';
import { useRoleApi } from '@/app/system-manager/api/application';
import CustomTable from '@/components/custom-table';
import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import PermissionWrapper from "@/components/permission";
import PermissionRule from '@/app/system-manager/components/application/permissionRule';
import {
  DataItem,
  PermissionRuleItem,
  PermissionConfig
} from '@/app/system-manager/types/permission';

const { Search } = Input;

const convertPermissionsForApi = (
  moduleConfig: any
): PermissionRuleItem[] => {
  const permissionArray: PermissionRuleItem[] = [];
  
  const config = moduleConfig;

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

  if (config.type === 'specific') {
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
    
    // 当specificData为空或者没有任何有效权限时，添加占位项来标识用户选择了specific类型
    // 这确保了即使用户取消了所有选择，模块配置仍然会被保存
    if (permissionArray.length === 0) {
      permissionArray.push({
        id: '-1',
        name: 'specific',
        permission: []
      });
    }
  }

  return permissionArray;
};

const convertApiDataToFormData = (
  items: PermissionRuleItem[]
): PermissionConfig => {
  const hasWildcard = items.some(item => item.id === '0');
  const hasEmptySpecific = items.some(item => item.id === '-1');

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
    specificData: hasEmptySpecific ? [] : items
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

const createDefaultPermissionRule = (modules: string[], moduleConfigs?: any[]): Record<string, any> => {
  const defaultPermissionRule: Record<string, any> = {};

  modules.forEach(module => {
    const moduleConfig = moduleConfigs?.find(config => config.name === module);
    
    if (moduleConfig?.children && moduleConfig.children.length > 0) {
      const buildDefaultNestedStructure = (children: any[]): Record<string, any> => {
        const nestedStructure: Record<string, any> = {};
        
        children.forEach(child => {
          if (!child.children || child.children.length === 0) {
            nestedStructure[child.name] = {
              type: 'specific',
              allPermissions: { view: true, operate: true },
              specificData: []
            };
          } else {
            nestedStructure[child.name] = buildDefaultNestedStructure(child.children);
          }
        });
        
        return nestedStructure;
      };
      
      defaultPermissionRule[module] = buildDefaultNestedStructure(moduleConfig.children);
    } else {
      defaultPermissionRule[module] = {
        type: 'specific',
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

  const [supportedModules, setSupportedModules] = useState<string[]>([]);
  const [moduleConfigLoading, setModuleConfigLoading] = useState(false);
  const [moduleConfigs, setModuleConfigs] = useState<any[]>([]);

  const {
    getGroupDataRule,
    deleteGroupDataRule,
    addGroupDataRule,
    updateGroupDataRule,
    getAppModules
  } = useRoleApi();

  const fetchAppModules = useCallback(async () => {
    if (!clientId || moduleConfigLoading) return;

    try {
      setModuleConfigLoading(true);
      const modules = await getAppModules({ params: { app: clientId } });
      const moduleNames = buildModulesMap(modules);
      setSupportedModules(moduleNames);
      setModuleConfigs(modules);
    } catch (error) {
      console.error('Failed to fetch app modules:', error);
      setSupportedModules([]);
      setModuleConfigs([]);
    } finally {
      setModuleConfigLoading(false);
    }
  }, [clientId]);

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
      const params: any = { app: clientId, page: currentPage, page_size: pageSize };
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

    const defaultPermissionRule = createDefaultPermissionRule(supportedModules, moduleConfigs);

    if (data) {
      const formattedPermissionRule: Record<string, any> = {};
      if (data.rules) {
        const convertApiDataToFormDataRecursive = (rulesData: any): any => {
          const result: Record<string, any> = {};
          
          Object.keys(rulesData).forEach(key => {
            const value = rulesData[key];
            
            if (Array.isArray(value) && value.length > 0 && 
                value.every(item => item.hasOwnProperty('id') && item.hasOwnProperty('permission'))) {
              result[key] = convertApiDataToFormData(value);
            } else if (value && typeof value === 'object' && !Array.isArray(value)) {
              result[key] = convertApiDataToFormDataRecursive(value);
            }
          });
          
          return result;
        };

        Object.keys(data.rules).forEach(moduleKey => {
          const moduleRules = data.rules[moduleKey];
          
          const hasNestedStructure = typeof moduleRules === 'object' && 
                                   !Array.isArray(moduleRules) &&
                                   Object.values(moduleRules).some(val => 
                                     Array.isArray(val) || (val && typeof val === 'object')
                                   );

          if (hasNestedStructure) {
            formattedPermissionRule[moduleKey] = convertApiDataToFormDataRecursive(moduleRules);
          } else {
            const items = Array.isArray(moduleRules) ? moduleRules : [];
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

    fetchAppModules();

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

      const collectLeafNodes = (config: any, currentPath: string[] = []): Array<{path: string[], leafName: string}> => {
        const leafNodes: Array<{path: string[], leafName: string}> = [];
        
        if (!config || typeof config !== 'object') {
          return leafNodes;
        }
        
        for (const key in config) {
          const value = config[key];
          if (value && typeof value === 'object' && value !== null) {
            if (typeof value.type !== 'undefined') {
              const fullPath = [...currentPath, key];
              leafNodes.push({
                path: fullPath,
                leafName: key
              });
            } else {
              const childLeafNodes = collectLeafNodes(value, [...currentPath, key]);
              leafNodes.push(...childLeafNodes);
            }
          }
        }
        
        return leafNodes;
      };

      const processModuleConfig = (moduleKey: string, moduleConfig: any) => {
        const isReallyFlatStructure = typeof moduleConfig.type !== 'undefined';

        if (!isReallyFlatStructure) {
          const leafNodes = collectLeafNodes(moduleConfig);
          
          const buildNestedRules = (leafNodes: Array<{path: string[], leafName: string}>) => {
            const nestedRules: Record<string, any> = {};
            
            leafNodes.forEach(({path, leafName}) => {
              let targetConfig = moduleConfig;
              for (const pathSegment of path) {
                if (targetConfig && typeof targetConfig === 'object') {
                  targetConfig = targetConfig[pathSegment];
                }
              }
              
              if (targetConfig && typeof targetConfig.type !== 'undefined') {
                const permissionArray = convertPermissionsForApi(targetConfig);

                if (permissionArray.length > 0) {
                  if (path.length === 1) {
                    nestedRules[leafName] = permissionArray;
                  } else {
                    let currentLevel = nestedRules;
                    
                    for (let i = 0; i < path.length - 1; i++) {
                      const pathSegment = path[i];
                      if (!currentLevel[pathSegment]) {
                        currentLevel[pathSegment] = {};
                      }
                      currentLevel = currentLevel[pathSegment];
                    }
                    
                    currentLevel[leafName] = permissionArray;
                  }
                }
              }
            });
            
            return nestedRules;
          };
          
          const moduleRules = buildNestedRules(leafNodes);

          if (Object.keys(moduleRules).length > 0) {
            transformedRules[moduleKey] = moduleRules;
          }
        } else {
          const permissionArray = convertPermissionsForApi(moduleConfig);

          if (permissionArray.length > 0) {
            transformedRules[moduleKey] = permissionArray;
          }
        }
      };

      supportedModules.forEach(moduleKey => {
        const moduleConfig = values.permissionRule[moduleKey];
        if (!moduleConfig) return;
        
        processModuleConfig(moduleKey, moduleConfig);
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
        type: 'custom',
        label: t('system.data.group'),
        rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.data.group')}` }],
        component: (
          <GroupTreeSelect
            multiple={false}
            placeholder={`${t('common.inputMsg')}${t('system.data.group')}`}
            onChange={(value: number | number[] | undefined) => {
              const groupId = Array.isArray(value) ? value[0] : value;
              if (groupId) {
                setCurrentGroupId(groupId.toString());
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
            }}
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
              onConfirm={() => handleDelete(record)}
            >
              <Button type="link">
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
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
