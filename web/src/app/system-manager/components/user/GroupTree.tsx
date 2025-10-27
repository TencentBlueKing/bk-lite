import React from 'react';
import { Input, Button, Tree, Dropdown, Menu } from 'antd';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface ExtendedTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
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
}

const GroupTree: React.FC<GroupTreeProps> = ({
  treeData,
  searchValue,
  onSearchChange,
  onAddRootGroup,
  onTreeSelect,
  onGroupAction,
  t,
}) => {
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

    return (
      <Dropdown
        overlay={
          <Menu
            onClick={({ key, domEvent }) => {
              domEvent.stopPropagation();
              onGroupAction(key, groupKey);
            }}
            items={[
              {
                key: 'addSubGroup',
                label: (
                  <PermissionWrapper requiredPermissions={['Add Group']}>
                    {t('system.group.addSubGroups')}
                  </PermissionWrapper>
                ),
              },
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
                disabled: isDefaultGroup,
                label: (
                  <PermissionWrapper requiredPermissions={['Delete Group']}>
                    {t('common.delete')}
                  </PermissionWrapper>
                ),
              },
            ]}
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

  const renderTreeNode = (nodes: ExtendedTreeDataNode[]): ExtendedTreeDataNode[] =>
    nodes.map((node) => ({
      ...node,
      selectable: node.hasAuth !== false,
      title: (
        <div className="flex justify-between items-center w-full pr-1">
          <EllipsisWithTooltip 
            text={typeof node.title === 'function' ? String(node.title(node)) : String(node.title)}
            className={`truncate max-w-[100px] flex-1 ${node.hasAuth === false ? 'opacity-50' : ''}`}
          />
          <span className="flex-shrink-0 ml-2">
            {renderGroupActions(node.key as number)}
          </span>
        </div>
      ),
      children: node.children ? renderTreeNode(node.children) : [],
    }));

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
      <Tree
        className="w-full flex-1 overflow-auto"
        showLine
        blockNode
        expandAction={false}
        defaultExpandAll
        treeData={renderTreeNode(treeData)}
        onSelect={onTreeSelect}
      />
    </div>
  );
};

export default GroupTree;