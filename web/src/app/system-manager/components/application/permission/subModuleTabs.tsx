import React, { useState, useEffect } from 'react';
import { Tabs } from 'antd';
import {
  SubModuleTabsProps,
  ProviderPermissionConfig,
  PermissionConfig
} from '@/app/system-manager/types/permission';
import { ModuleItem } from '@/app/system-manager/constants/application';
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
  // Current selected first-level module
  const [activeFirstLevel, setActiveFirstLevel] = useState<string>('');

  // Add current active leaf node state
  const [currentLeafNode, setCurrentLeafNode] = useState<string>('');

  // 添加一个状态来跟踪之前的模块
  const [previousModule, setPreviousModule] = useState<string>('');

  // Get current module configuration
  const currentModuleConfig = moduleTree?.[module];
  
  // Initialize default values when module config changes
  useEffect(() => {
    if (!currentModuleConfig?.children || currentModuleConfig.children.length === 0) {
      return;
    }

    const firstChild = currentModuleConfig.children[0];
    
    // 自动选择第一级的第一个模块
    if (!activeFirstLevel || module !== previousModule) {
      setActiveFirstLevel(firstChild?.name || '');
    }

    const initializeLeafNode = () => {
      if (firstChild) {
        if (!firstChild.children || firstChild.children.length === 0) {
          // First level is a leaf node
          const leafNode = firstChild.name;
          setCurrentLeafNode(leafNode);
          setActiveSubModule(leafNode);
        } else {
          // Has sub-levels, find the first leaf node
          const findFirstLeaf = (node: ModuleItem): string => {
            if (!node.children || node.children.length === 0) {
              return node.name;
            }
            return findFirstLeaf(node.children[0]);
          };
          const leafNode = findFirstLeaf(firstChild);
          setCurrentLeafNode(leafNode);
          setActiveSubModule(leafNode);
        }
      }
    };

    initializeLeafNode();
  }, [currentModuleConfig, module]); // 移除 activeFirstLevel 依赖，使用 module 变化来触发初始化

  useEffect(() => {
    if (module !== previousModule) {
      setPreviousModule(module);
      // 重置状态，强制重新初始化
      setActiveFirstLevel('');
      setCurrentLeafNode('');
    }
  }, [module, previousModule]);

  // Early return after all hooks are called
  if (!currentModuleConfig || !currentModuleConfig.children || currentModuleConfig.children.length === 0) {
    return null;
  }

  // Build first-level tab items - each tab has its own independent content
  const firstLevelTabs = currentModuleConfig.children.map(child => {
    // Generate content for each tab separately
    const tabContent = child.name === activeFirstLevel ? getContentForChild(child) : <div />;
    
    return {
      key: child.name,
      label: child.display_name || child.name,
      children: tabContent
    };
  });

  // Generate content for specified child module
  function getContentForChild(child: ModuleItem): React.ReactElement {
    // If has children, show second level
    if (child.children && child.children.length > 0) {
      return renderSecondLevel(child.children);
    }

    // Leaf node, directly render permission configuration
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
  }

  // Render second level
  function renderSecondLevel(children: ModuleItem[]): React.ReactElement {
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
            
            // Find corresponding child and load data
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
  }

  // Load leaf node data
  function loadDataForLeafNode(leafNodeKey: string) {
    const providerConfig = permissions[module] as ProviderPermissionConfig;
    
    // 使用递归查找来定位叶子节点配置
    const findLeafConfig = (config: any, targetKey: string): PermissionConfig | undefined => {
      if (config[targetKey] && typeof config[targetKey] === 'object' && config[targetKey].type !== undefined) {
        return config[targetKey] as PermissionConfig;
      }
      
      for (const key in config) {
        const value = config[key];
        if (value && typeof value === 'object' && value.type === undefined) {
          const found = findLeafConfig(value, targetKey);
          if (found) return found;
        }
      }
      return undefined;
    };
    
    const subModuleConfig = findLeafConfig(providerConfig, leafNodeKey);
    if (subModuleConfig?.type === 'specific' && (!moduleData[`${module}_${leafNodeKey}`] || moduleData[`${module}_${leafNodeKey}`].length === 0)) {
      loadSpecificData(module, leafNodeKey);
    }
  }

  // First level tab change handler
  const handleFirstLevelChange = (key: string) => {
    setActiveFirstLevel(key);
    
    // Find selected first-level child module
    const selectedChild = currentModuleConfig.children?.find(child => child.name === key);
    if (selectedChild) {
      // If first level is leaf node, directly load data
      if (!selectedChild.children || selectedChild.children.length === 0) {
        const leafNode = selectedChild.name;
        setCurrentLeafNode(leafNode);
        setActiveSubModule(leafNode);
        loadDataForLeafNode(leafNode);
      } else {
        // If has sub-levels, automatically select first child item
        const findFirstLeaf = (node: ModuleItem): string => {
          if (!node.children || node.children.length === 0) {
            return node.name;
          }
          return findFirstLeaf(node.children[0]);
        };
        
        const leafNode = findFirstLeaf(selectedChild);
        setCurrentLeafNode(leafNode);
        setActiveSubModule(leafNode);
        loadDataForLeafNode(leafNode);
      }
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
