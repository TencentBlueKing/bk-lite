import React, { useState, useEffect } from 'react';
import { Tabs } from 'antd';
import type {
  SubModuleTabsProps,
  ProviderPermissionConfig
} from '@/app/system-manager/types/permission';
import type { ModuleItem } from '@/app/system-manager/constants/application';
import {
  findPermissionInTree,
  getFirstLeafModule
} from '@/app/system-manager/utils/permissionTreeUtils';
import ModuleContent from './moduleContent';
import styles from './tabs.module.scss';

const SubModuleTabs: React.FC<SubModuleTabsProps> = ({
  module,
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
  handleTableChange,
  moduleTree
}) => {
  const [activeFirstLevel, setActiveFirstLevel] = useState<string>('');
  const [currentLeafNode, setCurrentLeafNode] = useState<string>('');
  const [previousModule, setPreviousModule] = useState<string>('');

  const currentModuleConfig = moduleTree?.[module];

  useEffect(() => {
    if (!currentModuleConfig?.children || currentModuleConfig.children.length === 0) {
      return;
    }

    const firstChild = currentModuleConfig.children[0];

    if (!activeFirstLevel || module !== previousModule) {
      setActiveFirstLevel(firstChild?.name || '');
    }

    const initializeLeafNode = () => {
      if (firstChild) {
        const leafNode = getFirstLeafModule(firstChild);
        setCurrentLeafNode(leafNode);
        setActiveSubModule(leafNode);
      }
    };

    initializeLeafNode();
  }, [currentModuleConfig, module, activeFirstLevel, previousModule, setActiveSubModule]);

  useEffect(() => {
    if (module !== previousModule) {
      setPreviousModule(module);
      setActiveFirstLevel('');
      setCurrentLeafNode('');
    }
  }, [module, previousModule]);

  if (!currentModuleConfig || !currentModuleConfig.children || currentModuleConfig.children.length === 0) {
    return null;
  }

  const loadDataForLeafNode = (leafNodeKey: string) => {
    const providerConfig = permissions[module] as ProviderPermissionConfig;
    const subModuleConfig = findPermissionInTree(providerConfig, leafNodeKey);

    if (subModuleConfig?.type === 'specific' && (!moduleData[`${module}_${leafNodeKey}`] || moduleData[`${module}_${leafNodeKey}`].length === 0)) {
      loadSpecificData(module, leafNodeKey);
    }
  };

  const renderSecondLevel = (children: ModuleItem[]): React.ReactElement => {
    const secondLevelTabs = children.map(child => ({
      key: child.name,
      label: child.display_name || child.name,
      children: child.name === currentLeafNode ? (
        <ModuleContent
          module={module}
          subModule={child.name}
          permissions={permissions}
          loading={loading}
          moduleData={moduleData}
          pagination={pagination}
          activeKey={activeKey}
          activeSubModule={child.name}
          handleTypeChange={handleTypeChange}
          handleAllPermissionChange={handleAllPermissionChange}
          handleSpecificDataChange={handleSpecificDataChange}
          handleTableChange={handleTableChange}
        />
      ) : <div />
    }));

    return (
      <div className={styles['nested-sub-module-tabs']}>
        <Tabs
          type="card"
          size="small"
          activeKey={currentLeafNode || children[0]?.name}
          onChange={(key) => {
            setCurrentLeafNode(key);
            setActiveSubModule(key);

            const selectedChild = children.find(c => c.name === key);
            if (selectedChild && (!selectedChild.children || selectedChild.children.length === 0)) {
              loadDataForLeafNode(key);
            }
          }}
          items={secondLevelTabs}
          tabBarStyle={{
            marginBottom: 16,
            overflowX: 'auto',
            scrollbarWidth: 'none'
          }}
        />
      </div>
    );
  };

  const getContentForChild = (child: ModuleItem): React.ReactElement => {
    if (child.children && child.children.length > 0) {
      return renderSecondLevel(child.children);
    }

    return (
      <ModuleContent
        module={module}
        subModule={child.name}
        permissions={permissions}
        loading={loading}
        moduleData={moduleData}
        pagination={pagination}
        activeKey={activeKey}
        activeSubModule={child.name}
        handleTypeChange={handleTypeChange}
        handleAllPermissionChange={handleAllPermissionChange}
        handleSpecificDataChange={handleSpecificDataChange}
        handleTableChange={handleTableChange}
      />
    );
  };

  const firstLevelTabs = currentModuleConfig.children.map(child => {
    const tabContent = child.name === activeFirstLevel ? getContentForChild(child) : <div />;

    return {
      key: child.name,
      label: child.display_name || child.name,
      children: tabContent
    };
  });

  const handleFirstLevelChange = (key: string) => {
    setActiveFirstLevel(key);

    const selectedChild = currentModuleConfig.children?.find(child => child.name === key);
    if (selectedChild) {
      const leafNode = getFirstLeafModule(selectedChild);
      setCurrentLeafNode(leafNode);
      setActiveSubModule(leafNode);
      loadDataForLeafNode(leafNode);
    }
  };

  return (
    <div className={styles['sub-module-tabs']}>
      <Tabs
        type="card"
        size="small"
        activeKey={activeFirstLevel}
        onChange={handleFirstLevelChange}
        items={firstLevelTabs}
        tabBarStyle={{
          marginBottom: 16,
          overflowX: 'auto',
          scrollbarWidth: 'none'
        }}
      />
    </div>
  );
};

export default SubModuleTabs;
