import React from 'react';
import { Tree, Input, Tag } from 'antd';
import { DeleteOutlined, SettingOutlined, SearchOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  getSubtreeKeys,
  getDeletableSubtreeKeys,
  cleanSelectedKeys,
  isNodeDisabled
} from '@/app/system-manager/utils/roleTreeUtils';

interface NodeHandlers {
  onPermissionSetting: (node: TreeDataNode, e: React.MouseEvent) => void;
  onRemove: (newKeys: number[]) => void;
}

interface TransferRightTreeProps {
  treeData: TreeDataNode[];
  filteredRightData: TreeDataNode[];
  selectedKeys: number[];
  organizationRoleIds: number[];
  rightSearchValue: string;
  rightExpandedKeys: React.Key[];
  disabled: boolean;
  loading: boolean;
  mode: 'group' | 'role';
  forceOrganizationRole: boolean;
  t: (key: string) => string;
  onSearchChange: (value: string) => void;
  onExpandedKeysChange: (keys: React.Key[]) => void;
  onChange: (keys: number[]) => void;
  onPermissionSetting?: (node: TreeDataNode, e: React.MouseEvent) => void;
}

function transformRightTreeGroup(
  nodes: TreeDataNode[],
  treeData: TreeDataNode[],
  selectedKeys: number[],
  handlers: NodeHandlers
): TreeDataNode[] {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    const isNodeSelected = selectedKeys.includes(node.key as number);

    if (node.children && node.children.length > 0) {
      const transformedChildren = transformRightTreeGroup(node.children, treeData, selectedKeys, handlers);

      if (isNodeSelected) {
        acc.push({
          ...node,
          title: (
            <div className="flex justify-between items-center w-full">
              <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
              <div>
                <SettingOutlined
                  className="cursor-pointer text-[var(--color-text-4)] mr-2"
                  onClick={(e) => handlers.onPermissionSetting(node, e)}
                />
                <DeleteOutlined
                  className="cursor-pointer text-[var(--color-text-4)]"
                  onClick={e => {
                    e.stopPropagation();
                    const keysToRemove = getSubtreeKeys(node);
                    let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                    updated = cleanSelectedKeys(updated, treeData);
                    handlers.onRemove(updated);
                  }}
                />
              </div>
            </div>
          ),
          children: transformedChildren
        });
      } else if (transformedChildren.length > 0) {
        acc.push({
          ...node,
          title: typeof node.title === 'function' ? node.title(node) : node.title,
          children: transformedChildren
        });
      }
    } else {
      if (isNodeSelected) {
        acc.push({
          ...node,
          title: (
            <div className="flex justify-between items-center w-full">
              <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
              <div>
                <SettingOutlined
                  className="cursor-pointer text-[var(--color-text-4)] mr-2"
                  onClick={(e) => handlers.onPermissionSetting(node, e)}
                />
                <DeleteOutlined
                  className="cursor-pointer text-[var(--color-text-4)]"
                  onClick={e => {
                    e.stopPropagation();
                    const keysToRemove = getSubtreeKeys(node);
                    let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                    updated = cleanSelectedKeys(updated, treeData);
                    handlers.onRemove(updated);
                  }}
                />
              </div>
            </div>
          )
        });
      }
    }
    return acc;
  }, []);
}

function transformRightTreeRole(
  nodes: TreeDataNode[],
  treeData: TreeDataNode[],
  selectedKeys: number[],
  organizationRoleIds: number[],
  forceOrganizationRole: boolean,
  t: (key: string) => string,
  onRemove: (newKeys: number[]) => void
): TreeDataNode[] {
  return nodes.map(node => {
    const isDisabled = isNodeDisabled(node);
    const isOrgRole = forceOrganizationRole || isDisabled || organizationRoleIds.includes(node.key as number);
    const isLeafNode = !node.children || node.children.length === 0;
    const canDelete = !isOrgRole;

    return {
      ...node,
      title: (
        <div className="flex justify-between items-center w-full">
          <div className="flex items-center gap-2">
            <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
            {isLeafNode && isOrgRole && (
              <Tag className='font-mini' color="orange">
                {t('system.role.organizationRole')}
              </Tag>
            )}
            {isLeafNode && !isOrgRole && (
              <Tag className='font-mini' color="blue">
                {t('system.role.personalRole')}
              </Tag>
            )}
          </div>
          {canDelete && (
            <DeleteOutlined
              className="cursor-pointer text-[var(--color-text-4)]"
              onClick={e => {
                e.stopPropagation();
                const keysToRemove = getDeletableSubtreeKeys(node, organizationRoleIds);
                let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                updated = cleanSelectedKeys(updated, treeData);
                onRemove(updated);
              }}
            />
          )}
        </div>
      ),
      children: node.children ? transformRightTreeRole(
        node.children,
        treeData,
        selectedKeys,
        organizationRoleIds,
        forceOrganizationRole,
        t,
        onRemove
      ) : []
    };
  });
}

const TransferRightTree: React.FC<TransferRightTreeProps> = ({
  treeData,
  filteredRightData,
  selectedKeys,
  organizationRoleIds,
  rightSearchValue,
  rightExpandedKeys,
  disabled,
  loading,
  mode,
  forceOrganizationRole,
  t,
  onSearchChange,
  onExpandedKeysChange,
  onChange,
  onPermissionSetting
}) => {
  const transformedData = React.useMemo(() => {
    if (mode === 'group') {
      return transformRightTreeGroup(treeData, treeData, selectedKeys, {
        onPermissionSetting: onPermissionSetting || (() => {}),
        onRemove: onChange
      });
    }

    return transformRightTreeRole(
      filteredRightData,
      treeData,
      selectedKeys,
      organizationRoleIds,
      forceOrganizationRole,
      t,
      onChange
    );
  }, [filteredRightData, treeData, selectedKeys, onChange, organizationRoleIds, mode, onPermissionSetting, forceOrganizationRole, t]);

  return (
    <div className="flex flex-col w-full">
      <div className="p-2">
        <Input
          prefix={<SearchOutlined />}
          placeholder={t('common.search')}
          value={rightSearchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          allowClear
        />
      </div>
      <div className="w-full p-1 max-h-[250px] overflow-auto">
        <Tree
          blockNode
          selectable={false}
          expandedKeys={rightExpandedKeys}
          onExpand={(keys) => onExpandedKeysChange(keys)}
          treeData={transformedData}
          disabled={disabled || loading}
        />
      </div>
    </div>
  );
};

export default TransferRightTree;
