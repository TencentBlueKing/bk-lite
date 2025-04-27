import React from 'react';
import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  SubModuleTabsProps,
  ProviderPermissionConfig,
  PermissionConfig
} from '@/app/system-manager/types/permission';
import {
  SUB_MODULE_MAP,
  EDITABLE_MODULES
} from '@/app/system-manager/constants/application';
import ModuleContent from './moduleContent';

const SubModuleTabs: React.FC<SubModuleTabsProps> = ({
  module,
  activeSubModule,
  setActiveSubModule,
  permissions,
  moduleData,
  loadSpecificData,
  loading,
  pagination,
  activeKey,
  handleTypeChange,
  handleAllPermissionChange,
  handleSpecificDataChange,
  handleTableChange
}) => {
  const { t } = useTranslation();

  if (!SUB_MODULE_MAP[module]) return null;

  const subModules = SUB_MODULE_MAP[module];
  if (subModules.length === 0) return null;

  const subItems = subModules.map(subModule => ({
    key: subModule,
    label: t(`system.modules.${subModule}`) || subModule,
    children: (
      <ModuleContent
        module={module}
        subModule={subModule}
        permissions={permissions}
        loading={loading}
        moduleData={moduleData}
        pagination={pagination}
        activeKey={activeKey}
        activeSubModule={activeSubModule || ''}
        handleTypeChange={handleTypeChange}
        handleAllPermissionChange={handleAllPermissionChange}
        handleSpecificDataChange={handleSpecificDataChange}
        handleTableChange={handleTableChange}
      />
    )
  }));

  return (
    <Tabs
      activeKey={activeSubModule || subModules[0]}
      onChange={(key) => {
        setActiveSubModule(key);

        if (!EDITABLE_MODULES.includes(key)) {
          return;
        }

        const providerConfig = permissions[module] as ProviderPermissionConfig;

        if (providerConfig[key]) {
          const subModuleConfig = providerConfig[key] as PermissionConfig;

          if (subModuleConfig.type === 'specific' && (!moduleData[`${module}_${key}`] || moduleData[`${module}_${key}`].length === 0)) {
            loadSpecificData(module, key);
          }
        }
      }}
      items={subItems}
      className="sub-module-tabs"
    />
  );
};

export default SubModuleTabs;
