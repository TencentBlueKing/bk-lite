import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Transfer, Spin } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import PermissionModal from './permissionModal';
import TransferLeftTree from './transferLeftTree';
import TransferRightTree from './transferRightTree';
import {
  flattenRoleData,
  filterTreeData,
  getSubtreeKeys,
  getAllKeys,
  filterTreeNode,
  getSearchExpandedKeys,
  getAllLeafNodes,
  type FlattenedRole
} from './role-tree-utils';

const areKeysEqual = (left: React.Key[], right: React.Key[]) => {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((key, index) => String(key) === String(right[index]));
};

interface TreeTransferProps {
  treeData: TreeDataNode[];
  selectedKeys: React.Key[];
  personalRoleIds?: React.Key[];
  groupRules?: { [key: string]: { [app: string]: number } };
  permissionClientModules?: string[];
  fetchGroupDataRule?: (params: {
    params: { group_id: string };
  }) => Promise<any[]>;
  onChange: (newKeys: React.Key[]) => void;
  onChangeRule?: (newKey: number, newRules: { [app: string]: number }) => void;
  mode?: 'group' | 'role';
  disabled?: boolean;
  loading?: boolean;
  forceOrganizationRole?: boolean;
  organizationRoleIds?: React.Key[];
  organizationRoleSourceMap?: Record<string, string>;
  enableSubGroupSelect?: boolean;
  inheritedRoleIds?: React.Key[];
  inheritedRoleSourceMap?: Record<string, string>;
}

export { flattenRoleData };

const RoleTransfer: React.FC<TreeTransferProps> = ({
  treeData,
  selectedKeys,
  personalRoleIds = [],
  groupRules = {},
  permissionClientModules,
  fetchGroupDataRule,
  onChange,
  onChangeRule,
  mode = 'role',
  disabled = false,
  loading = false,
  forceOrganizationRole = false,
  organizationRoleIds = [],
  organizationRoleSourceMap = {},
  enableSubGroupSelect = false,
  inheritedRoleIds = [],
  inheritedRoleSourceMap = {},
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

    let newSelectedKeys: React.Key[] = [...selectedKeys];

    if (includeAll) {
      const allChildrenIds = getSubtreeKeys(node);
      const idsToAdd = allChildrenIds.filter(id => !newSelectedKeys.some((key) => String(key) === String(id)));
      newSelectedKeys = [...newSelectedKeys, ...idsToAdd];
    } else {
      const allChildrenIds = getSubtreeKeys(node);
      newSelectedKeys = newSelectedKeys.filter(id => !allChildrenIds.some((key) => String(key) === String(id)));
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
    const nextExpandedKeys = leftSearchValue
      ? getSearchExpandedKeys(treeData, leftSearchValue)
      : getAllKeys(treeData);

    setLeftExpandedKeys((prevKeys) => (areKeysEqual(prevKeys, nextExpandedKeys) ? prevKeys : nextExpandedKeys));
  }, [leftSearchValue, treeData]);

  const filteredRightData = useMemo(() => {
    const allRightKeys = [...new Map([...selectedKeys, ...inheritedRoleIds].map((key) => [String(key), key])).values()];
    let filtered = filterTreeData(treeData, allRightKeys);

    if (rightSearchValue) {
      filtered = filtered
        .map(node => filterTreeNode(node, rightSearchValue))
        .filter(Boolean) as TreeDataNode[];
    }

    return filtered;
  }, [treeData, selectedKeys, inheritedRoleIds, rightSearchValue]);

  useEffect(() => {
    const nextExpandedKeys = rightSearchValue
      ? getSearchExpandedKeys(filteredRightData, rightSearchValue)
      : getAllKeys(filteredRightData);

    setRightExpandedKeys((prevKeys) => (areKeysEqual(prevKeys, nextExpandedKeys) ? prevKeys : nextExpandedKeys));
  }, [rightSearchValue, filteredRightData]);

  const flattenedRoleData = useMemo(() => flattenRoleData(leftTreeData), [leftTreeData]);

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
          targetKeys={selectedKeys.map((key) => String(key))}
          className="tree-transfer"
          render={(item) => item.title}
          showSelectAll={false}
          disabled={disabled || loading}
          onChange={(nextTargetKeys) => {
            if (!disabled && !loading) {
              onChange(nextTargetKeys);
            }
          }}
        >
          {({ direction }) => {
            if (direction === 'left') {
              const leftTreePersonalRoleIds = forceOrganizationRole ? selectedKeys : personalRoleIds;
              const leftTreeOrganizationRoleIds = forceOrganizationRole ? inheritedRoleIds : organizationRoleIds;

              return (
                <TransferLeftTree
                  treeData={leftTreeData}
                  selectedKeys={selectedKeys}
                  personalRoleIds={leftTreePersonalRoleIds}
                  organizationRoleIds={leftTreeOrganizationRoleIds}
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
                  personalRoleIds={personalRoleIds}
                  organizationRoleIds={organizationRoleIds}
                  organizationRoleSourceMap={organizationRoleSourceMap}
                  inheritedRoleIds={inheritedRoleIds}
                  inheritedRoleSourceMap={inheritedRoleSourceMap}
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
          clientModules={permissionClientModules || []}
          fetchGroupDataRule={fetchGroupDataRule || (async () => [])}
          onOk={handlePermissionOk}
          onCancel={() => setIsPermissionModalVisible(false)}
        />
      )}
    </>
  );
};

export type {
  PermissionData,
  AppPermission,
  PermissionFormValues,
  PermissionModalProps,
} from './types';
export default RoleTransfer;
