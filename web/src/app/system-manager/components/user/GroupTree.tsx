import React from 'react';
import { Input, Button, Tree, Dropdown, Menu, Skeleton } from 'antd';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import Icon from '@/components/icon';

interface ExtendedTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
  isVirtual?: boolean;
  parentIsVirtual?: boolean;
  children?: ExtendedTreeDataNode[];
}

interface GroupTreeProps {
  treeData: ExtendedTreeDataNode[];
  searchValue: string;
  onSearchChange: (value: string) => void;
  onAddRootGroup: () => void;
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
  onTreeSelect,
  onGroupAction,
  t,
  loading = false,
}) => {
  // Helper function to check if a node's parent is virtual
  const isNodeChildOfVirtual = (tree: ExtendedTreeDataNode[], targetKey: number): boolean => {
    for (const node of tree) {
      // Check if any of the children is the target node
      if (node.children) {
        for (const child of node.children) {
          if (child.key === targetKey) {
            // Found the target node, check if its parent (current node) is virtual
            return node.isVirtual === true;
          }
        }
        // Continue searching in children
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
    
    // 判断是否为顶层虚拟团队（自己是虚拟团队且父节点不是虚拟团队）
    const isVirtual = node?.isVirtual === true;
    const hasVirtualParent = isNodeChildOfVirtual(treeData, groupKey);
    const isTopLevelVirtualGroup = isVirtual && !hasVirtualParent;
    
    // 虚拟团队的子级不能再添加子级
    const canAddSubGroup = !hasVirtualParent;

    const menuItems = [
      ...(canAddSubGroup ? [{
        key: 'addSubGroup',
        label: (
          <PermissionWrapper requiredPermissions={['Add Group']}>
            {t('system.group.addSubGroups')}
          </PermissionWrapper>
        ),
      }] : []),
      {
        key: 'edit',
        label: (
          <PermissionWrapper requiredPermissions={['Edit Group']}>
            {t('common.edit')}
          </PermissionWrapper>
        ),
      },
      {
        key: 'delete',
        disabled: isDefaultGroup || isTopLevelVirtualGroup,
        label: (
          <PermissionWrapper requiredPermissions={['Delete Group']}>
            {t('common.delete')}
          </PermissionWrapper>
        ),
      },
    ];

    return (
      <Dropdown
        overlay={
          <Menu
            onClick={({ key, domEvent }) => {
              domEvent.stopPropagation();
              onGroupAction(key, groupKey);
            }}
            items={menuItems}
          />
        }
        trigger={['click']}
      >
        <MoreOutlined
          className="cursor-pointer"
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
          }}
        />
      </Dropdown>
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
        <PermissionWrapper requiredPermissions={['Add Group']}>
          <Button 
            type="primary" 
            size="small" 
            icon={<PlusOutlined />} 
            className="ml-2" 
            onClick={onAddRootGroup}
          />
        </PermissionWrapper>
      </div>
      {loading ? (
        <div className="w-full flex-1 overflow-auto p-4">
          <Skeleton active paragraph={{ rows: 6 }} />
        </div>
      ) : (
        <Tree
          className="w-full flex-1 overflow-auto"
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