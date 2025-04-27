import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Tabs } from 'antd';
import type { RadioChangeEvent } from 'antd';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import { useSearchParams } from 'next/navigation';
import { useRoleApi } from '@/app/system-manager/api/application';
import { useTranslation } from '@/utils/i18n';

import {
  PermissionRuleProps,
  PermissionsState,
  ModulePermissionConfig,
  ProviderPermissionConfig,
  PermissionConfig,
  DataPermission,
  PaginationInfo
} from '@/app/system-manager/types/permission';
import {
  SUB_MODULE_MAP,
  EDITABLE_MODULES
} from '@/app/system-manager/constants/application';
import ModuleContent from './permission/moduleContent';
import SubModuleTabs from './permission/subModuleTabs';

const PermissionRule: React.FC<PermissionRuleProps> = ({
  value = {},
  modules = [],
  onChange,
  formGroupId
}) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const clientId = searchParams ? searchParams.get('clientId') : null;
  const { getAppData } = useRoleApi();
  const [initialized, setInitialized] = useState(false);
  const renderCount = useRef(0);
  const isInitialRender = useRef(true);
  const prevFormGroupId = useRef<string | null>(null);
  const prevActiveKey = useRef<string | null>(null);
  const prevActiveSubModule = useRef<string | null>(null);
  const effectRunCount = useRef<{ [key: string]: number }>({});

  const [permissions, setPermissions] = useState<PermissionsState>(() => {
    renderCount.current += 1;

    const initialPermissions: PermissionsState = {};
    const hasValue = value && Object.keys(value).length > 0;

    modules.forEach(module => {
      if (module === 'provider') {
        const providerConfig: ProviderPermissionConfig = { __type: 'provider' };
        SUB_MODULE_MAP[module].forEach(subModule => {
          providerConfig[subModule] = {
            type: hasValue && value[module]?.[subModule]?.type || 'all',
            allPermissions: {
              view: hasValue && value[module]?.[subModule]?.allPermissions?.view !== undefined
                ? value[module]?.[subModule]?.allPermissions?.view
                : true,
              operate: hasValue && value[module]?.[subModule]?.allPermissions?.operate !== undefined
                ? value[module]?.[subModule]?.allPermissions?.operate
                : true
            },
            specificData: hasValue && value[module]?.[subModule]?.specificData
              ? value[module]?.[subModule]?.specificData.map((item: DataPermission) => ({
                ...item,
                operate: item.operate === true
              })) : []
          };
        });
        initialPermissions[module] = providerConfig;
      } else {
        initialPermissions[module] = {
          __type: 'module',
          type: hasValue && value[module]?.type || 'all',
          allPermissions: {
            view: hasValue && value[module]?.allPermissions?.view !== undefined
              ? value[module]?.allPermissions?.view
              : true,
            operate: hasValue && value[module]?.allPermissions?.operate !== undefined
              ? value[module]?.allPermissions?.operate
              : true
          },
          specificData: hasValue && value[module]?.specificData
            ? value[module]?.specificData.map((item: DataPermission) => ({
              ...item,
              operate: item.operate === true
            })) : []
        };
      }
    });

    return initialPermissions;
  });

  const [loading, setLoading] = useState<{ [key: string]: boolean }>({});
  const [moduleData, setModuleData] = useState<{ [key: string]: any[] }>({});
  const [pagination, setPagination] = useState<{ [key: string]: { current: number, pageSize: number, total: number } }>({});
  const [activeKey, setActiveKey] = useState<string>(modules.length > 0 ? modules[0] : '');
  const [activeSubModule, setActiveSubModule] = useState<string>('');

  useEffect(() => {
    if (!isInitialRender.current) return;

    isInitialRender.current = false;

    return () => {
      // Cleanup on unmount
    };
  }, []);

  useEffect(() => {
    if (!formGroupId || formGroupId === prevFormGroupId.current) return;

    prevFormGroupId.current = formGroupId;

    setModuleData({});
    setPagination({});
  }, [formGroupId]);

  useEffect(() => {
    if (!value || Object.keys(value).length === 0) {
      if (initialized) {
        const defaultPermissions: PermissionsState = {};
        modules.forEach(module => {
          if (module === 'provider') {
            const providerConfig: ProviderPermissionConfig = { __type: 'provider' };
            SUB_MODULE_MAP[module].forEach(subModule => {
              providerConfig[subModule] = {
                type: 'all',
                allPermissions: { view: true, operate: true },
                specificData: []
              };
            });
            defaultPermissions[module] = providerConfig;
          } else {
            defaultPermissions[module] = {
              __type: 'module',
              type: 'all',
              allPermissions: { view: true, operate: true },
              specificData: []
            };
          }
        });
        setPermissions(defaultPermissions);
      }
      return;
    }

    setInitialized(true);

    const newPermissions: PermissionsState = {};
    modules.forEach(module => {
      if (module === 'provider') {
        const providerConfig: ProviderPermissionConfig = { __type: 'provider' };
        SUB_MODULE_MAP[module].forEach(subModule => {
          providerConfig[subModule] = {
            type: value[module]?.[subModule]?.type || 'all',
            allPermissions: {
              view: value[module]?.[subModule]?.allPermissions?.view !== undefined
                ? value[module]?.[subModule]?.allPermissions?.view
                : true,
              operate: value[module]?.[subModule]?.allPermissions?.operate !== undefined
                ? value[module]?.[subModule]?.allPermissions?.operate
                : true
            },
            specificData: value[module]?.[subModule]?.specificData || []
          };
        });
        newPermissions[module] = providerConfig;
      } else {
        newPermissions[module] = {
          __type: 'module',
          type: value[module]?.type || 'all',
          allPermissions: {
            view: value[module]?.allPermissions?.view !== undefined
              ? value[module]?.allPermissions?.view
              : true,
            operate: value[module]?.allPermissions?.operate !== undefined
              ? value[module]?.allPermissions?.operate
              : true
          },
          specificData: value[module]?.specificData || []
        };
      }
    });

    const currentJSON = JSON.stringify(permissions);
    const newJSON = JSON.stringify(newPermissions);

    if (currentJSON !== newJSON) {
      setPermissions(newPermissions);
      setModuleData({});

      if (activeKey) {
        if (activeKey === 'provider' && activeSubModule) {
          const config = newPermissions[activeKey] as ProviderPermissionConfig;
          const subConfig = config[activeSubModule] as PermissionConfig;
          if (subConfig?.type === 'specific') {
            loadSpecificData(activeKey, activeSubModule);
          }
        } else {
          const config = newPermissions[activeKey] as ModulePermissionConfig;
          if (config?.type === 'specific') {
            loadSpecificData(activeKey);
          }
        }
      }
    }
  }, [value, modules, initialized, activeKey, activeSubModule]);

  const loadSpecificData = useCallback(async (module: string, subModule?: string) => {
    const dataKey = subModule ? `${module}_${subModule}` : module;

    if (loading[dataKey]) {
      return;
    }

    try {
      setLoading(prev => ({ ...prev, [dataKey]: true }));

      const paginationInfo = pagination[dataKey] || { current: 1, pageSize: 10, total: 0 };

      const params: Record<string, any> = {
        app: clientId,
        module,
        child_module: '',
        page: paginationInfo.current,
        page_size: paginationInfo.pageSize,
        group_id: formGroupId
      };

      if (subModule) {
        params.child_module = subModule;
      }

      const data = await getAppData({ params });

      const currentPermissions = permissions;

      const formattedData = data.items.map((item: any) => {
        let currentPermission;
        if (subModule) {
          const providerConfig = currentPermissions[module] as ProviderPermissionConfig;
          const subModuleConfig = providerConfig[subModule] as PermissionConfig;
          currentPermission = subModuleConfig.specificData?.find(p => p.id === item.id);
        } else {
          const moduleConfig = currentPermissions[module] as ModulePermissionConfig;
          currentPermission = moduleConfig.specificData?.find(p => p.id === item.id);
        }

        return {
          ...item,
          view: currentPermission?.view ?? false,
          operate: currentPermission?.operate ?? false
        };
      });

      setModuleData(prev => ({
        ...prev,
        [dataKey]: formattedData
      }));

      setPagination(prev => ({
        ...prev,
        [dataKey]: {
          ...paginationInfo,
          total: data.count
        }
      }));
    } catch (error) {
      console.error('Failed to load specific data:', error);
    } finally {
      setLoading(prev => ({ ...prev, [dataKey]: false }));
    }
  }, [clientId, formGroupId, pagination, getAppData, loading]);

  useEffect(() => {
    if (!initialized) return;

    const effectKey = `${activeKey}-${activeSubModule}`;

    if (
      activeKey === prevActiveKey.current &&
      activeSubModule === prevActiveSubModule.current &&
      effectRunCount.current[effectKey] > 0
    ) {
      return;
    }

    prevActiveKey.current = activeKey;
    prevActiveSubModule.current = activeSubModule;
    effectRunCount.current[effectKey] = (effectRunCount.current[effectKey] || 0) + 1;

    if (activeKey === 'provider' && activeSubModule) {
      const providerConfig = permissions[activeKey] as ProviderPermissionConfig;
      if (providerConfig && providerConfig[activeSubModule]) {
        const subConfig = providerConfig[activeSubModule] as PermissionConfig;
        if (subConfig?.type === 'specific') {
          loadSpecificData(activeKey, activeSubModule);
        }
      }
    } else if (activeKey !== 'provider') {
      const moduleConfig = permissions[activeKey] as ModulePermissionConfig;
      if (moduleConfig?.type === 'specific') {
        loadSpecificData(activeKey);
      }
    }
  }, [activeKey, activeSubModule, initialized, permissions]);

  const handleTypeChange = useCallback((e: RadioChangeEvent, module: string, subModule?: string) => {
    const newPermissions = { ...permissions };

    if (subModule && module === 'provider') {
      const providerConfig = newPermissions[module] as ProviderPermissionConfig;

      if (!providerConfig[subModule]) {
        providerConfig[subModule] = {
          type: 'all',
          allPermissions: { view: true, operate: true },
          specificData: []
        };
      }

      (providerConfig[subModule] as PermissionConfig).type = e.target.value;

      if (e.target.value === 'specific') {
        loadSpecificData(module, subModule);
      }
    } else {
      const moduleConfig = newPermissions[module] as ModulePermissionConfig;
      moduleConfig.type = e.target.value;

      if (e.target.value === 'specific') {
        loadSpecificData(module);
      }
    }

    setPermissions(newPermissions);
    if (onChange) {
      onChange(newPermissions);
    }
  }, [permissions, onChange]);

  const handleAllPermissionChange = useCallback((e: CheckboxChangeEvent, module: string, type: 'view' | 'operate', subModule?: string) => {
    const newPermissions = { ...permissions };

    if (subModule && module === 'provider') {
      const providerConfig = newPermissions[module] as ProviderPermissionConfig;
      if (!providerConfig[subModule]) return;

      const subModuleConfig = providerConfig[subModule] as PermissionConfig;

      if (type === 'view') {
        subModuleConfig.allPermissions.view = e.target.checked;

        if (!e.target.checked) {
          subModuleConfig.allPermissions.operate = false;
        }
      } else if (type === 'operate') {
        if (subModuleConfig.allPermissions.view) {
          subModuleConfig.allPermissions.operate = e.target.checked;
        }
      }
    } else {
      const moduleConfig = newPermissions[module] as ModulePermissionConfig;

      if (type === 'view') {
        moduleConfig.allPermissions.view = e.target.checked;

        if (!e.target.checked) {
          moduleConfig.allPermissions.operate = false;
        }
      } else if (type === 'operate') {
        if (moduleConfig.allPermissions.view) {
          moduleConfig.allPermissions.operate = e.target.checked;
        }
      }
    }

    setPermissions(newPermissions);

    if (onChange) {
      onChange(newPermissions);
    }
  }, [permissions, onChange]);

  const handleSpecificDataChange = useCallback((record: DataPermission, module: string, type: 'view' | 'operate', subModule?: string) => {
    const newPermissions = { ...permissions };
    const dataKey = subModule ? `${module}_${subModule}` : module;

    setModuleData(prev => {
      const newData = [...(prev[dataKey] || [])];
      const itemIndex = newData.findIndex(item => item.id === record.id);

      if (itemIndex > -1) {
        if (type === 'view') {
          newData[itemIndex] = {
            ...newData[itemIndex],
            view: record.view
          };

          if (!record.view) {
            newData[itemIndex].operate = false;
          }
        } else if (type === 'operate') {
          if (newData[itemIndex].view) {
            newData[itemIndex] = {
              ...newData[itemIndex],
              operate: record.operate
            };
          }
        }
      }

      return { ...prev, [dataKey]: newData };
    });

    if (subModule && module === 'provider') {
      const providerConfig = newPermissions[module] as ProviderPermissionConfig;
      if (!providerConfig[subModule]) return;

      const subModuleConfig = providerConfig[subModule] as PermissionConfig;
      if (!subModuleConfig.specificData) subModuleConfig.specificData = [];

      const dataIndex = subModuleConfig.specificData.findIndex(item => item.id === record.id);

      if (dataIndex === -1) {
        subModuleConfig.specificData.push(record);
      } else {
        const item = { ...subModuleConfig.specificData[dataIndex] };
        if (type === 'view') {
          item.view = record.view;
          if (!record.view) {
            item.operate = false;
          }
        } else if (type === 'operate') {
          if (item.view) {
            item.operate = record.operate;
          }
        }

        subModuleConfig.specificData[dataIndex] = item;
      }
    } else {
      const moduleConfig = newPermissions[module] as ModulePermissionConfig;
      if (!moduleConfig.specificData) moduleConfig.specificData = [];

      const dataIndex = moduleConfig.specificData.findIndex(item => item.id === record.id);

      if (dataIndex === -1) {
        moduleConfig.specificData.push(record);
      } else {
        const item = { ...moduleConfig.specificData[dataIndex] };
        if (type === 'view') {
          item.view = record.view;
          if (!record.view) {
            item.operate = false;
          }
        } else if (type === 'operate') {
          if (item.view) {
            item.operate = record.operate;
          }
        }

        moduleConfig.specificData[dataIndex] = item;
      }
    }

    setPermissions(newPermissions);
    if (onChange) {
      onChange(newPermissions);
    }
  }, [permissions, onChange]);

  const handleTableChange = async (pagination: PaginationInfo, filters: any, sorter: any, module?: string, subModule?: string) => {
    if (!module) return;

    const dataKey = subModule ? `${module}_${subModule}` : module;

    setPagination(prev => ({
      ...prev,
      [dataKey]: {
        current: pagination.current,
        pageSize: pagination.pageSize,
        total: prev[dataKey]?.total || 0
      }
    }));

    try {
      setLoading(prev => ({ ...prev, [dataKey]: true }));

      const params: Record<string, any> = {
        app: clientId,
        module,
        page: pagination.current,
        page_size: pagination.pageSize,
        group_id: formGroupId
      };

      if (subModule) {
        params.child_module = subModule;
      }

      const data = await getAppData({ params });

      const formattedData = data.items.map((item: any) => {
        let currentPermission;
        if (subModule) {
          const providerConfig = permissions[module] as ProviderPermissionConfig;
          const subModuleConfig = providerConfig[subModule] as PermissionConfig;
          currentPermission = subModuleConfig.specificData?.find(p => p.id === item.id);
        } else {
          const moduleConfig = permissions[module] as ModulePermissionConfig;
          currentPermission = moduleConfig.specificData?.find(p => p.id === item.id);
        }

        return {
          ...item,
          view: currentPermission?.view ?? false,
          operate: currentPermission?.operate ?? false
        };
      });

      setModuleData(prev => ({
        ...prev,
        [dataKey]: formattedData
      }));
    } catch (error) {
      console.error('Failed to load specific data:', error);
    } finally {
      setLoading(prev => ({ ...prev, [dataKey]: false }));
    }
  };

  const items = modules.map(module => ({
    key: module,
    label: t(`system.modules.${module}`) || module,
    children: module === 'provider'
      ? (
        <SubModuleTabs
          module={module}
          activeSubModule={activeSubModule}
          setActiveSubModule={setActiveSubModule}
          permissions={permissions}
          moduleData={moduleData}
          loadSpecificData={loadSpecificData}
          loading={loading}
          pagination={pagination}
          activeKey={activeKey}
          handleTypeChange={handleTypeChange}
          handleAllPermissionChange={handleAllPermissionChange}
          handleSpecificDataChange={handleSpecificDataChange}
          handleTableChange={handleTableChange}
        />
      )
      : (
        <ModuleContent
          module={module}
          permissions={permissions}
          loading={loading}
          moduleData={moduleData}
          pagination={pagination}
          activeKey={activeKey}
          activeSubModule={activeSubModule}
          handleTypeChange={handleTypeChange}
          handleAllPermissionChange={handleAllPermissionChange}
          handleSpecificDataChange={handleSpecificDataChange}
          handleTableChange={handleTableChange}
        />
      )
  }));

  if (modules.length === 0) {
    return <div>{t('system.permission.noAvailableModules')}</div>;
  }

  return (
    <Tabs
      activeKey={activeKey}
      onChange={(key) => {
        if (key === activeKey) return;

        setActiveKey(key);

        if (key === 'provider' && SUB_MODULE_MAP[key] && SUB_MODULE_MAP[key].length > 0) {
          const firstSubModule = SUB_MODULE_MAP[key][0];
          setActiveSubModule(firstSubModule);

          if (!EDITABLE_MODULES.includes(firstSubModule)) {
            return;
          }

          const providerConfig = permissions[key] as ProviderPermissionConfig;
          const subModuleConfig = providerConfig[firstSubModule] as PermissionConfig;

          if (subModuleConfig?.type === 'specific') {
            loadSpecificData(key, firstSubModule);
          }
        } else if (key !== 'provider') {
          if (!EDITABLE_MODULES.includes(key)) {
            return;
          }

          const moduleConfig = permissions[key] as ModulePermissionConfig;

          if (moduleConfig?.type === 'specific') {
            loadSpecificData(key);
          }
        }
      }}
      items={items}
      className="permission-rule-tabs"
    />
  );
};

export default React.memo(PermissionRule);

