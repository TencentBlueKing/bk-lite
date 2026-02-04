import React from 'react';
import { Tree, Input, Checkbox } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  isFullySelected,
  processLeftTreeData,
  isNodeDisabled
} from '@/app/system-manager/utils/roleTreeUtils';

interface TransferLeftTreeProps {
  treeData: TreeDataNode[];
  selectedKeys: number[];
  organizationRoleIds: number[];
  leftSearchValue: string;
  leftExpandedKeys: React.Key[];
  disabled: boolean;
  loading: boolean;
  mode: 'group' | 'role';
  enableSubGroupSelect: boolean;
  t: (key: string) => string;
  onSearchChange: (value: string) => void;
  onExpandedKeysChange: (keys: React.Key[]) => void;
  onChange: (keys: number[]) => void;
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void;
}

function renderTreeNodeTitle(
  node: TreeDataNode,
  selectedKeys: number[],
  enableSubGroupSelect: boolean,
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void,
  t: (key: string) => string
): React.ReactNode {
  const hasChildren = node.children && node.children.length > 0;
  const nodeTitle = typeof node.title === 'function' ? node.title(node) : node.title;

  if (!hasChildren || !enableSubGroupSelect) {
    return nodeTitle;
  }

  const isAllSubGroupsSelected = isFullySelected(node, selectedKeys);

  return (
    <div className="flex items-center justify-between w-full" onClick={(e) => e.stopPropagation()}>
      <span>{nodeTitle}</span>
      <Checkbox
        checked={isAllSubGroupsSelected}
        onChange={(e) => {
          e.stopPropagation();
          onSubGroupToggle(node, e.target.checked);
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <span className="text-xs">{t('system.user.selectAllSubGroups')}</span>
      </Checkbox>
    </div>
  );
}

function transformLeftTreeData(
  nodes: TreeDataNode[],
  selectedKeys: number[],
  enableSubGroupSelect: boolean,
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void,
  t: (key: string) => string,
  organizationRoleIds: number[]
): TreeDataNode[] {
  return nodes.map(node => ({
    ...node,
    title: renderTreeNodeTitle(node, selectedKeys, enableSubGroupSelect, onSubGroupToggle, t),
    disabled: node.disabled || organizationRoleIds.includes(node.key as number),
    children: node.children ? transformLeftTreeData(
      node.children,
      selectedKeys,
      enableSubGroupSelect,
      onSubGroupToggle,
      t,
      organizationRoleIds
    ) : undefined
  }));
}

const TransferLeftTree: React.FC<TransferLeftTreeProps> = ({
  treeData,
  selectedKeys,
  organizationRoleIds,
  leftSearchValue,
  leftExpandedKeys,
  disabled,
  loading,
  mode,
  enableSubGroupSelect,
  t,
  onSearchChange,
  onExpandedKeysChange,
  onChange,
  onSubGroupToggle
}) => {
  const processedTreeData = React.useMemo(() => {
    if (mode === 'group' && enableSubGroupSelect) {
      return transformLeftTreeData(
        treeData,
        selectedKeys,
        enableSubGroupSelect,
        onSubGroupToggle,
        t,
        organizationRoleIds
      );
    }
    return processLeftTreeData(treeData, organizationRoleIds);
  }, [treeData, selectedKeys, enableSubGroupSelect, onSubGroupToggle, t, mode, organizationRoleIds]);

  const handleCheck = React.useCallback((checkedKeys: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }, info: { checkedNodes: TreeDataNode[] }) => {
    if (disabled || loading) return;

    const validCheckedNodes = info.checkedNodes.filter((node) =>
      !isNodeDisabled(node) && !organizationRoleIds.includes(node.key as number)
    );
    const newKeys = validCheckedNodes.map((node) => node.key as number);

    const existingOrgRoles = selectedKeys.filter(key => organizationRoleIds.includes(key));
    const finalKeys = [...new Set([...newKeys, ...existingOrgRoles])];

    onChange(finalKeys);
  }, [disabled, loading, organizationRoleIds, selectedKeys, onChange]);

  return (
    <div className="flex flex-col">
      <div className="p-2">
        <Input
          prefix={<SearchOutlined />}
          placeholder={t('common.search')}
          value={leftSearchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          allowClear
        />
      </div>
      <div className="p-1 max-h-[250px] overflow-auto">
        <Tree
          blockNode
          checkable
          selectable={false}
          checkStrictly={mode === 'group'}
          expandedKeys={leftExpandedKeys}
          onExpand={(keys) => onExpandedKeysChange(keys)}
          checkedKeys={mode === 'group' ? { checked: selectedKeys, halfChecked: [] } : selectedKeys}
          treeData={processedTreeData}
          disabled={disabled || loading}
          onCheck={handleCheck}
        />
      </div>
    </div>
  );
};

export default TransferLeftTree;
