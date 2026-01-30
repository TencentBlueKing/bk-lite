import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Transfer, Spin } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import PermissionModal from './permissionModal';
import TransferLeftTree from './TransferLeftTree';
import TransferRightTree from './TransferRightTree';
import {
  flattenRoleData,
  filterTreeData,
  getSubtreeKeys,
  getAllKeys,
  filterTreeNode,
  getSearchExpandedKeys,
  getAllLeafNodes,
  type FlattenedRole
} from '@/app/system-manager/utils/roleTreeUtils';

interface TreeTransferProps {
  treeData: TreeDataNode[];
  selectedKeys: number[];
  groupRules?: { [key: string]: { [app: string]: number } };
  onChange: (newKeys: number[]) => void;
  onChangeRule?: (newKey: number, newRules: { [app: string]: number }) => void;
  mode?: 'group' | 'role';
  disabled?: boolean;
  loading?: boolean;
  forceOrganizationRole?: boolean;
  organizationRoleIds?: number[];
  enableSubGroupSelect?: boolean;
}

export { flattenRoleData };

const RoleTransfer: React.FC<TreeTransferProps> = ({
  treeData,
  selectedKeys,
  groupRules = {},
  onChange,
  onChangeRule,
  mode = 'role',
  disabled = false,
  loading = false,
  forceOrganizationRole = false,
  organizationRoleIds = [],
  enableSubGroupSelect = false,
}) => {
  const { t } = useTranslation();
  const [isPermissionModalVisible, setIsPermissionModalVisible] = useState<boolean>(false);
  const [currentNode, setCurrentNode] = useState<TreeDataNode | null>(null);
  const [currentRules, setCurrentRules] = useState<{ [app: string]: number }>({});
  const [leftSearchValue, setLeftSearchValue] = useState<string>('');
  const [rightSearchValue, setRightSearchValue] = useState<string>('');
  const [leftExpandedKeys, setLeftExpandedKeys] = useState<React.Key[]>([]);
  const [rightExpandedKeys, setRightExpandedKeys] = useState<React.Key[]>([]);

  const handleSubGroupToggle = useCallback((node: TreeDataNode, includeAll: boolean) => {
    if (disabled || loading) return;

    let newSelectedKeys = [...selectedKeys];

    if (includeAll) {
      const allChildrenIds = getSubtreeKeys(node);
      const idsToAdd = allChildrenIds.filter(id => !newSelectedKeys.includes(id));
      newSelectedKeys = [...newSelectedKeys, ...idsToAdd];
    } else {
      const allChildrenIds = getSubtreeKeys(node);
      newSelectedKeys = newSelectedKeys.filter(id => !allChildrenIds.includes(id));
    }

    onChange(newSelectedKeys);
  }, [selectedKeys, onChange, disabled, loading]);

  const leftTreeData = useMemo(() => {
    if (!leftSearchValue) return treeData;

    return treeData
      .map(node => filterTreeNode(node, leftSearchValue))
      .filter(Boolean) as TreeDataNode[];
  }, [treeData, leftSearchValue]);

  useEffect(() => {
    if (leftSearchValue) {
      setLeftExpandedKeys(getSearchExpandedKeys(treeData, leftSearchValue));
    } else {
      setLeftExpandedKeys(getAllKeys(treeData));
    }
  }, [leftSearchValue, treeData]);

  const flattenedRoleData = useMemo(() => flattenRoleData(leftTreeData), [leftTreeData]);

  const filteredRightData = useMemo(() => {
    let filtered = filterTreeData(treeData, selectedKeys);

    if (rightSearchValue) {
      filtered = filtered
        .map(node => filterTreeNode(node, rightSearchValue))
        .filter(Boolean) as TreeDataNode[];
    }

    return filtered;
  }, [treeData, selectedKeys, rightSearchValue]);

  useEffect(() => {
    if (rightSearchValue) {
      setRightExpandedKeys(getSearchExpandedKeys(filteredRightData, rightSearchValue));
    } else {
      setRightExpandedKeys(getAllKeys(filteredRightData));
    }
  }, [rightSearchValue, filteredRightData]);

  const handlePermissionSetting = useCallback((node: TreeDataNode, e: React.MouseEvent) => {
    e.stopPropagation();
    setCurrentNode(node);
    const nodeKey = node.key as number;
    const rules = groupRules[nodeKey] || {};
    setCurrentRules(rules);
    setIsPermissionModalVisible(true);
  }, [groupRules]);

  const handlePermissionOk = useCallback((values: { permissions?: Array<{ app: string; permission: number }> }) => {
    if (!currentNode || !onChangeRule) return;

    const appPermissionMap: { [app: string]: number } = {};
    values?.permissions?.forEach((permission) => {
      if (permission.permission !== 0) {
        appPermissionMap[permission.app] = permission.permission;
      }
    });

    const nodeKey = currentNode.key as number;
    onChangeRule(nodeKey, appPermissionMap);
    setIsPermissionModalVisible(false);
  }, [currentNode, onChangeRule]);

  const transferDataSource = useMemo((): FlattenedRole[] => {
    if (mode === 'group') {
      return getAllLeafNodes(treeData);
    }
    return flattenedRoleData;
  }, [treeData, mode, flattenedRoleData]);

  return (
    <>
      <Spin spinning={loading}>
        <Transfer
          oneWay
          dataSource={transferDataSource}
          targetKeys={selectedKeys}
          className="tree-transfer"
          render={(item) => item.title}
          showSelectAll={false}
          disabled={disabled || loading}
          onChange={(nextTargetKeys) => {
            if (!disabled && !loading) {
              onChange(nextTargetKeys as number[]);
            }
          }}
        >
          {({ direction }) => {
            if (direction === 'left') {
              return (
                <TransferLeftTree
                  treeData={leftTreeData}
                  selectedKeys={selectedKeys}
                  organizationRoleIds={organizationRoleIds}
                  leftSearchValue={leftSearchValue}
                  leftExpandedKeys={leftExpandedKeys}
                  disabled={disabled}
                  loading={loading}
                  mode={mode}
                  enableSubGroupSelect={enableSubGroupSelect}
                  t={t}
                  onSearchChange={setLeftSearchValue}
                  onExpandedKeysChange={setLeftExpandedKeys}
                  onChange={onChange}
                  onSubGroupToggle={handleSubGroupToggle}
                />
              );
            } else if (direction === 'right') {
              return (
                <TransferRightTree
                  treeData={treeData}
                  filteredRightData={filteredRightData}
                  selectedKeys={selectedKeys}
                  organizationRoleIds={organizationRoleIds}
                  rightSearchValue={rightSearchValue}
                  rightExpandedKeys={rightExpandedKeys}
                  disabled={disabled}
                  loading={loading}
                  mode={mode}
                  forceOrganizationRole={forceOrganizationRole}
                  t={t}
                  onSearchChange={setRightSearchValue}
                  onExpandedKeysChange={setRightExpandedKeys}
                  onChange={onChange}
                  onPermissionSetting={onChangeRule ? handlePermissionSetting : undefined}
                />
              );
            }
          }}
        </Transfer>
      </Spin>
      {currentNode && (
        <PermissionModal
          visible={isPermissionModalVisible}
          rules={currentRules}
          node={currentNode}
          onOk={handlePermissionOk}
          onCancel={() => setIsPermissionModalVisible(false)}
        />
      )}
    </>
  );
};

export default RoleTransfer;
