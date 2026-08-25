import React, { useMemo } from 'react';
import { Input, Button, Tree, Skeleton, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import Icon from '@/components/icon';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import usePermissions from '@/hooks/usePermissions';

interface ExtendedTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
  isVirtual?: boolean;
  parentIsVirtual?: boolean;
  syncSource?: number | null;
  children?: ExtendedTreeDataNode[];
}

interface GroupTreeProps {
  treeData: ExtendedTreeDataNode[];
  searchValue: string;
  onSearchChange: (value: string) => void;
  onAddRootGroup: () => void;
  onOpenArchivedDrawer?: () => void;
  onTreeSelect: (selectedKeys: React.Key[]) => void;
  onGroupAction: (action: string, groupKey: number) => void;
  t: (key: string) => string;
  loading?: boolean;
}

const GroupTree: React.FC<GroupTreeProps> = ({
  treeData,
  searchValue,
  onSearchChange,
  onAddRootGroup,
  onOpenArchivedDrawer,
  onTreeSelect,
  onGroupAction,
  t,
  loading = false,
}) => {
  const { hasPermission } = usePermissions();
  const canAddGroup = hasPermission(['Add Group']);
  const canDeleteGroup = hasPermission(['Delete Group']);
  const showRootActions = canAddGroup || canDeleteGroup;

  const isNodeChildOfVirtual = (tree: ExtendedTreeDataNode[], targetKey: number): boolean => {
    for (const node of tree) {
      if (node.children) {
        for (const child of node.children) {
          if (child.key === targetKey) {
            return node.isVirtual === true;
          }
        }
        const result = isNodeChildOfVirtual(node.children, targetKey);
        if (result) return result;
      }
    }
    return false;
  };

  const findNode = (tree: ExtendedTreeDataNode[], key: number): ExtendedTreeDataNode | undefined => {
    for (const node of tree) {
      if (node.key === key) return node;
      if (node.children) {
        const found = findNode(node.children, key);
        if (found) return found;
      }
    }
  };

  const renderGroupActions = (groupKey: number) => {
    const node = findNode(treeData, groupKey);
    if (node && node.hasAuth === false) {
      return null;
    }

    const nodeName = node ? (typeof node.title === 'string' ? node.title : String(node.title)) : '';
    const isDefaultGroup = nodeName === 'Default';

    const isVirtual = node?.isVirtual === true;
    const isSyncedGroup = node?.syncSource != null;
    const hasVirtualParent = isNodeChildOfVirtual(treeData, groupKey);
    const isTopLevelVirtualGroup = isVirtual && !hasVirtualParent;

    const canAddSubGroup = !hasVirtualParent && !isSyncedGroup;

    const menuItems = [
      ...(canAddSubGroup ? [{
        key: 'addSubGroup',
        label: t('system.group.addSubGroups'),
        permission: 'Add Group',
      }] : []),
      {
        key: 'edit',
        label: t('common.edit'),
        permission: 'Edit Group',
      },
      ...(node?.syncSource == null ? [{
        key: 'delete',
        disabled: isDefaultGroup || isTopLevelVirtualGroup,
        label: t('system.group.archive'),
        permission: 'Delete Group',
      }] : []),
    ];

    return (
      <MoreActionsDropdown
        items={menuItems.map((item) => ({
          key: String(item.key),
          label: item.label,
          permission: item.permission,
          disabled: 'disabled' in item ? item.disabled : undefined,
          onClick: () => onGroupAction(String(item.key), groupKey),
        }))}
        buttonClassName="cursor-pointer"
        stopPropagation
      />
    );
  };

  const renderTreeNode = (nodes: ExtendedTreeDataNode[], parentIsVirtual = false): ExtendedTreeDataNode[] =>
    nodes.map((node) => {
      const currentIsVirtual = node.isVirtual === true;
      const childParentIsVirtual = currentIsVirtual || parentIsVirtual;
      const iconType = currentIsVirtual ? 'xunituandui' : 'zuzhiqunzu';

      return {
        ...node,
        parentIsVirtual,
        selectable: node.hasAuth !== false,
        title: (
          <div className="flex justify-between items-center w-full pr-1">
            <div className="flex items-center gap-1 flex-1 min-w-0">
              <Icon type={iconType} className="flex-shrink-0 font-mini" />
              <EllipsisWithTooltip
                text={typeof node.title === 'function' ? String(node.title(node)) : String(node.title)}
                className={`truncate max-w-[100px] flex-1 ${node.hasAuth === false ? 'opacity-50' : ''}`}
              />
            </div>
            <span className="flex-shrink-0 ml-2">
              {renderGroupActions(node.key as number)}
            </span>
          </div>
        ),
        children: node.children ? renderTreeNode(node.children, childParentIsVirtual) : [],
      };
    });

  const rootMenuItems = useMemo((): MenuProps['items'] => {
    const items: MenuProps['items'] = [];
    if (canAddGroup) {
      items.push({
        key: 'addRoot',
        label: t('system.group.addRootGroup'),
        onClick: () => onAddRootGroup(),
      });
    }
    if (canDeleteGroup && onOpenArchivedDrawer) {
      items.push({
        key: 'restoreArchived',
        label: t('system.group.restoreArchivedGroup'),
        onClick: () => onOpenArchivedDrawer(),
      });
    }
    return items;
  }, [canAddGroup, canDeleteGroup, onAddRootGroup, onOpenArchivedDrawer, t]);

  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex items-center mb-4">
        <Input
          size="small"
          className="flex-1"
          placeholder={`${t('common.search')}...`}
          onChange={(e) => onSearchChange(e.target.value)}
          value={searchValue}
        />
        {showRootActions && (
          <Dropdown menu={{ items: rootMenuItems }} trigger={['click']}>
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              className="ml-2"
            />
          </Dropdown>
        )}
      </div>
      {loading ? (
        <div className="w-full flex-1 overflow-auto p-4">
          <Skeleton active paragraph={{ rows: 6 }} />
        </div>
      ) : (
        <Tree
          className="w-full flex-1 overflow-auto bg-transparent"
          showLine
          blockNode
          expandAction={false}
          defaultExpandAll
          treeData={renderTreeNode(treeData)}
          onSelect={onTreeSelect}
        />
      )}
    </div>
  );
};

export default GroupTree;
