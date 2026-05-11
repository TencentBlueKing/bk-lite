import React from 'react';
import { Tree, Input, Checkbox } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  isFullySelected,
  processLeftTreeData,
  isNodeDisabled
} from '@/app/system-manager/utils/roleTreeUtils';

const hasKey = (keys: React.Key[], targetKey: React.Key) =>
  keys.some((key) => String(key) === String(targetKey));

const getLeafRoleKeys = (node: TreeDataNode): React.Key[] => {
  if (!node.children || node.children.length === 0) {
    return [node.key];
  }

  return node.children.flatMap((child) => getLeafRoleKeys(child));
};

const getRoleNodeCheckState = (
  node: TreeDataNode,
  personalRoleIds: React.Key[],
  organizationRoleIds: React.Key[]
) => {
  const leafKeys = getLeafRoleKeys(node);
  const selectedLeafKeys = leafKeys.filter(
    (key) => hasKey(personalRoleIds, key) || hasKey(organizationRoleIds, key)
  );

  const checked = leafKeys.length > 0 && selectedLeafKeys.length === leafKeys.length;
  const indeterminate = selectedLeafKeys.length > 0 && selectedLeafKeys.length < leafKeys.length;

  if (!node.children || node.children.length === 0) {
    const isPersonalRole = hasKey(personalRoleIds, node.key);
    const isOrganizationRole = hasKey(organizationRoleIds, node.key);

    return {
      checked: isPersonalRole,
      indeterminate: !isPersonalRole && isOrganizationRole,
    };
  }

  return { checked, indeterminate };
};

interface TransferLeftTreeProps {
  treeData: TreeDataNode[];
  selectedKeys: React.Key[];
  personalRoleIds: React.Key[];
  organizationRoleIds: React.Key[];
  leftSearchValue: string;
  leftExpandedKeys: React.Key[];
  disabled: boolean;
  loading: boolean;
  mode: 'group' | 'role';
  enableSubGroupSelect: boolean;
  t: (key: string) => string;
  onSearchChange: (value: string) => void;
  onExpandedKeysChange: (keys: React.Key[]) => void;
  onChange: (keys: React.Key[]) => void;
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void;
}

function renderTreeNodeTitle(
  node: TreeDataNode,
  selectedKeys: React.Key[],
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
  selectedKeys: React.Key[],
  enableSubGroupSelect: boolean,
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void,
  t: (key: string) => string
): TreeDataNode[] {
  return nodes.map(node => ({
    ...node,
    title: renderTreeNodeTitle(node, selectedKeys, enableSubGroupSelect, onSubGroupToggle, t),
    children: node.children ? transformLeftTreeData(
      node.children,
      selectedKeys,
      enableSubGroupSelect,
      onSubGroupToggle,
      t
    ) : undefined
  }));
}

function transformRoleTreeData(
  nodes: TreeDataNode[],
  personalRoleIds: React.Key[],
  organizationRoleIds: React.Key[],
  disabled: boolean,
  loading: boolean,
  onChange: (keys: React.Key[]) => void
): TreeDataNode[] {
  return nodes.map((node) => {
    const { checked, indeterminate } = getRoleNodeCheckState(node, personalRoleIds, organizationRoleIds);
    const leafKeys = getLeafRoleKeys(node);
    const toggleNode = (nextChecked: boolean) => {
      if (disabled || loading) {
        return;
      }

      const nextPersonalRoleIds = nextChecked
        ? [...new Map([...personalRoleIds, ...leafKeys].map((key) => [String(key), key])).values()]
        : personalRoleIds.filter((key) => !leafKeys.some((leafKey) => String(leafKey) === String(key)));

      onChange(nextPersonalRoleIds);
    };

    return {
      ...node,
      disableCheckbox: true,
      title: (
        <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
          <Checkbox
            checked={checked}
            indeterminate={indeterminate}
            onChange={(event) => {
              event.stopPropagation();
              toggleNode(event.target.checked);
            }}
            onClick={(event) => event.stopPropagation()}
            disabled={disabled || loading}
          />
          <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
        </div>
      ),
      children: node.children
        ? transformRoleTreeData(node.children, personalRoleIds, organizationRoleIds, disabled, loading, onChange)
        : undefined,
    };
  });
}

const TransferLeftTree: React.FC<TransferLeftTreeProps> = ({
  treeData,
  selectedKeys,
  personalRoleIds,
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
        t
      );
    }

    if (mode === 'role') {
      return transformRoleTreeData(
        treeData,
        personalRoleIds,
        organizationRoleIds,
        disabled,
        loading,
        onChange
      );
    }

    return processLeftTreeData(treeData);
  }, [treeData, selectedKeys, enableSubGroupSelect, onSubGroupToggle, t, mode, personalRoleIds, organizationRoleIds, disabled, loading, onChange]);

  const handleCheck = React.useCallback((checkedKeys: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }, info: { checkedNodes: TreeDataNode[] }) => {
    if (disabled || loading) return;

    const validCheckedNodes = info.checkedNodes.filter((node) => !isNodeDisabled(node));
    const newKeys = validCheckedNodes.map((node) => node.key);

    onChange(newKeys);
  }, [disabled, loading, onChange]);

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
      <div className="overflow-auto p-1" style={{ maxHeight: 250 }}>
        <Tree
          blockNode
          checkable={mode === 'group'}
          selectable={false}
          checkStrictly={mode === 'group'}
          expandedKeys={leftExpandedKeys}
          onExpand={(keys) => onExpandedKeysChange(keys)}
          checkedKeys={mode === 'group' ? { checked: selectedKeys, halfChecked: [] } : undefined}
          treeData={processedTreeData}
          disabled={disabled || loading}
          onCheck={mode === 'group' ? handleCheck : undefined}
        />
      </div>
    </div>
  );
};

export default TransferLeftTree;
