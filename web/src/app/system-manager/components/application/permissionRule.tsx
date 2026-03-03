'use client';

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Tabs, Skeleton } from 'antd';
import type { RadioChangeEvent } from 'antd';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';

import type {
  PermissionRuleProps,
  PermissionsState,
  ModulePermissionConfig,
  ProviderPermissionConfig,
  PermissionConfig,
  DataPermission
} from '@/app/system-manager/types/permission';

import {
  useModuleConfig,
  usePermissionData,
  buildInitialPermissions
} from '@/app/system-manager/hooks/usePermissionData';
import {
  findPermissionInTree,
  getFirstLeafModule,
  isSubModuleOf,
  hasSubModules,
  deepClone,
  setNestedPermissionConfig,
  updateNestedAllPermission,
  updateNestedSpecificData
} from '@/app/system-manager/utils/permissionTreeUtils';

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

  const {
    moduleConfig,
    subModuleMap,
    editableModules,
    moduleTree,
    moduleConfigLoading,
    fetchModuleConfig
  } = useModuleConfig(clientId);

  const [permissions, setPermissions] = useState<PermissionsState>(() => {
    const hasValue = value && Object.keys(value).length > 0;
    return buildInitialPermissions({ moduleList: modules, hasValue, value, moduleTree });
  });

  const {
    loading,
    moduleData,
    pagination,
    loadSpecificData,
    handleTableChange
  } = usePermissionData(clientId, permissions, formGroupId);

  const [activeKey, setActiveKey] = useState<string>('');
  const [activeSubModule, setActiveSubModule] = useState<string>('');
  const debounceTimer = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (modules.length > 0 && moduleConfig.length === 0) {
      fetchModuleConfig();
    }
  }, [modules, moduleConfig.length, fetchModuleConfig]);

  useEffect(() => {
    if (moduleConfig.length > 0 && modules.length > 0) {
      const hasValue = value && Object.keys(value).length > 0;
      const newPermissions = buildInitialPermissions({ moduleList: modules, hasValue, value, moduleTree });
      setPermissions(newPermissions);
    }
  }, [moduleConfig, modules, value, moduleTree]);

  useEffect(() => {
    if (modules.length > 0 && Object.keys(moduleTree).length > 0 && !activeKey) {
      const firstModule = modules[0];
      setActiveKey(firstModule);

      const firstModuleConfig = moduleTree[firstModule];
      if (firstModuleConfig?.children && firstModuleConfig.children.length > 0) {
        const firstLeafModule = getFirstLeafModule(firstModuleConfig);
        setActiveSubModule(firstLeafModule);

        setTimeout(() => {
          if (editableModules.includes(firstLeafModule)) {
            const providerConfig = permissions[firstModule] as ProviderPermissionConfig;
            const subModuleConfig = findPermissionInTree(providerConfig, firstLeafModule);
            if (subModuleConfig?.type === 'specific') {
              loadSpecificData(firstModule, firstLeafModule);
            }
          }
        }, 100);
      } else {
        setActiveSubModule('');
        setTimeout(() => {
          if (editableModules.includes(firstModule)) {
            const modulePermConfig = permissions[firstModule] as ModulePermissionConfig;
            if (modulePermConfig?.type === 'specific') {
              loadSpecificData(firstModule);
            }
          }
        }, 100);
      }
    }
  }, [modules, moduleTree, activeKey, permissions, editableModules, loadSpecificData]);

  useEffect(() => {
    if (!activeKey || Object.keys(permissions).length === 0 || Object.keys(moduleTree).length === 0) {
      return;
    }

    const modulePermission = permissions[activeKey];
    if (!modulePermission) return;

    if (!hasSubModules(modulePermission)) {
      const modulePermConfig = modulePermission as ModulePermissionConfig;
      if (modulePermConfig.type === 'specific') {
        loadSpecificData(activeKey);
      }
    } else if (activeSubModule) {
      const providerConfig = modulePermission as ProviderPermissionConfig;
      const subModuleConfig = findPermissionInTree(providerConfig, activeSubModule);
      if (subModuleConfig?.type === 'specific') {
        loadSpecificData(activeKey, activeSubModule);
      }
    }
  }, [activeKey, activeSubModule, moduleTree, permissions, loadSpecificData]);

  const handleTypeChange = useCallback((e: RadioChangeEvent, module: string, subModule?: string) => {
    const newPermissions = { ...permissions };
    const modulePermission = newPermissions[module];
    const moduleHasSubModules = hasSubModules(modulePermission);

    if (subModule && moduleHasSubModules && isSubModuleOf(moduleTree, module, subModule)) {
      const providerConfig = { ...newPermissions[module] } as ProviderPermissionConfig;
      const currentConfig = findPermissionInTree(providerConfig, subModule);
      const updatedConfig: PermissionConfig = {
        type: e.target.value,
        allPermissions: currentConfig?.allPermissions || { view: true, operate: true },
        specificData: currentConfig?.specificData || []
      };

      const updateSuccess = setNestedPermissionConfig(providerConfig, subModule, updatedConfig);

      if (updateSuccess) {
        newPermissions[module] = providerConfig;
        if (e.target.value === 'specific') {
          loadSpecificData(module, subModule);
        }
      }
    } else {
      const modulePermConfig = { ...newPermissions[module] } as ModulePermissionConfig;
      modulePermConfig.type = e.target.value;
      newPermissions[module] = modulePermConfig;

      if (e.target.value === 'specific') {
        loadSpecificData(module);
      }
    }

    setPermissions(newPermissions);
    onChange?.(newPermissions);
  }, [permissions, moduleTree, onChange, loadSpecificData]);

  const handleAllPermissionChange = useCallback((
    e: CheckboxChangeEvent,
    module: string,
    type: 'view' | 'operate',
    subModule?: string
  ) => {
    const newPermissions = { ...permissions };
    const modulePermission = newPermissions[module];
    const moduleHasSubModules = hasSubModules(modulePermission);

    if (subModule && moduleHasSubModules && isSubModuleOf(moduleTree, module, subModule)) {
      const providerConfig = { ...newPermissions[module] } as ProviderPermissionConfig;
      const updateSuccess = updateNestedAllPermission(providerConfig, subModule, type, e.target.checked);
      if (updateSuccess) {
        newPermissions[module] = providerConfig;
      }
    } else {
      const modulePermConfig = {
        ...newPermissions[module],
        allPermissions: {
          ...(newPermissions[module] as ModulePermissionConfig).allPermissions
        }
      } as ModulePermissionConfig;

      if (type === 'view') {
        modulePermConfig.allPermissions.view = e.target.checked;
        if (!e.target.checked) {
          modulePermConfig.allPermissions.operate = false;
        }
      } else if (type === 'operate') {
        if (modulePermConfig.allPermissions.view) {
          modulePermConfig.allPermissions.operate = e.target.checked;
        }
      }

      newPermissions[module] = modulePermConfig;
    }

    setPermissions(newPermissions);
    onChange?.(newPermissions);
  }, [permissions, moduleTree, onChange]);

  const handleSpecificDataChange = useCallback((
    record: DataPermission,
    module: string,
    type: 'view' | 'operate',
    subModule?: string
  ) => {
    const newPermissions = { ...permissions };
    const modulePermission = newPermissions[module];
    const moduleHasSubModules = hasSubModules(modulePermission);

    if (subModule && moduleHasSubModules && isSubModuleOf(moduleTree, module, subModule)) {
      const clonedProviderConfig = deepClone(newPermissions[module]) as ProviderPermissionConfig;
      const updateSuccess = updateNestedSpecificData(clonedProviderConfig, subModule, record, type);

      if (updateSuccess) {
        newPermissions[module] = clonedProviderConfig;
      }
    } else {
      const modulePermConfig = {
        ...newPermissions[module],
        specificData: [...((newPermissions[module] as ModulePermissionConfig).specificData || [])]
      } as ModulePermissionConfig;

      const dataIndex = modulePermConfig.specificData.findIndex(item => item.id === record.id);

      if (dataIndex === -1) {
        modulePermConfig.specificData.push(record);
      } else {
        const item = { ...modulePermConfig.specificData[dataIndex] };
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
        modulePermConfig.specificData[dataIndex] = item;
      }

      newPermissions[module] = modulePermConfig;
    }

    setPermissions(newPermissions);

    if (onChange) {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
      debounceTimer.current = setTimeout(() => {
        onChange(newPermissions);
      }, 50);
    }
  }, [permissions, moduleTree, onChange]);

  const handleTabChange = useCallback((key: string) => {
    if (key === activeKey) return;

    setActiveKey(key);

    const tabModuleConfig = moduleTree[key];
    const tabHasSubModules = tabModuleConfig?.children && tabModuleConfig.children.length > 0;

    if (tabHasSubModules) {
      const firstLeafModule = getFirstLeafModule(tabModuleConfig);
      setActiveSubModule(firstLeafModule);

      if (editableModules.includes(firstLeafModule)) {
        const providerConfig = permissions[key] as ProviderPermissionConfig;
        const subModuleConfig = findPermissionInTree(providerConfig, firstLeafModule);
        if (subModuleConfig?.type === 'specific') {
          loadSpecificData(key, firstLeafModule);
        }
      }
    } else {
      setActiveSubModule('');

      if (editableModules.includes(key)) {
        const modulePermConfig = permissions[key] as ModulePermissionConfig;
        if (modulePermConfig?.type === 'specific') {
          loadSpecificData(key);
        }
      }
    }
  }, [activeKey, moduleTree, editableModules, permissions, loadSpecificData]);

  const tabItems = useMemo(() => {
    return modules.map(module => {
      const config = moduleTree[module];
      const moduleHasSubModules = config?.children && config.children.length > 0;

      return {
        key: module,
        label: moduleTree[module]?.display_name,
        children: moduleHasSubModules
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
              subModuleMap={subModuleMap}
              moduleTree={moduleTree}
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
      };
    });
  }, [
    modules,
    moduleTree,
    activeSubModule,
    permissions,
    moduleData,
    loading,
    pagination,
    activeKey,
    subModuleMap,
    handleTypeChange,
    handleAllPermissionChange,
    handleSpecificDataChange,
    handleTableChange,
    loadSpecificData
  ]);

  if (moduleConfigLoading) {
    return (
      <div className="permission-rule-skeleton">
        <Skeleton.Button active size="large" style={{ width: 120, marginRight: 16 }} />
        <Skeleton.Button active size="large" style={{ width: 100, marginRight: 16 }} />
        <Skeleton.Button active size="large" style={{ width: 140 }} />
        <div className="mt-6">
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      </div>
    );
  }

  if (modules.length === 0) {
    return <div>{t('system.permission.noAvailableModules')}</div>;
  }

  return (
    <Tabs
      activeKey={activeKey}
      onChange={handleTabChange}
      items={tabItems}
      className="permission-rule-tabs"
    />
  );
};

export default React.memo(PermissionRule);
