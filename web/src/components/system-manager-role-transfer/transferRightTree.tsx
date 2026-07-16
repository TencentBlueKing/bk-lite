import React from 'react';
import { Tree, Tag, Tooltip } from 'antd';
import { DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  getSubtreeKeys,
  getDeletableSubtreeKeys,
  cleanSelectedKeys,
  isNodeDisabled
} from './role-tree-utils';
import TransferTreePanel from '@/components/system-manager-transfer-tree-panel';

interface NodeHandlers {
  onPermissionSetting: (node: TreeDataNode, e: React.MouseEvent) => void;
  onRemove: (newKeys: React.Key[]) => void;
}

interface TransferRightTreeProps {
  treeData: TreeDataNode[];
  filteredRightData: TreeDataNode[];
  selectedKeys: React.Key[];
  personalRoleIds: React.Key[];
  organizationRoleIds: React.Key[];
  organizationRoleSourceMap: Record<string, string>;
  inheritedRoleIds: React.Key[];
  inheritedRoleSourceMap: Record<string, string>;
  rightSearchValue: string;
  rightExpandedKeys: React.Key[];
  disabled: boolean;
  loading: boolean;
  mode: 'group' | 'role';
  forceOrganizationRole: boolean;
  t: (key: string) => string;
  onSearchChange: (value: string) => void;
  onExpandedKeysChange: (keys: React.Key[]) => void;
  onChange: (keys: React.Key[]) => void;
  onPermissionSetting?: (node: TreeDataNode, e: React.MouseEvent) => void;
}

function transformRightTreeGroup(
  nodes: TreeDataNode[],
  treeData: TreeDataNode[],
  selectedKeys: React.Key[],
  handlers: NodeHandlers
): TreeDataNode[] {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    const isNodeSelected = selectedKeys.some((key) => String(key) === String(node.key));

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
                  className="mr-2 cursor-pointer text-(--color-text-4)"
                  onClick={(e) => handlers.onPermissionSetting(node, e)}
                />
                <DeleteOutlined
                  className="cursor-pointer text-(--color-text-4)"
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
                  className="mr-2 cursor-pointer text-(--color-text-4)"
                  onClick={(e) => handlers.onPermissionSetting(node, e)}
                />
                <DeleteOutlined
                  className="cursor-pointer text-(--color-text-4)"
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
  selectedKeys: React.Key[],
  personalRoleIds: React.Key[],
  organizationRoleIds: React.Key[],
  organizationRoleSourceMap: Record<string, string>,
  inheritedRoleIds: React.Key[],
  inheritedRoleSourceMap: Record<string, string>,
  forceOrganizationRole: boolean,
  t: (key: string) => string,
  onRemove: (newKeys: React.Key[]) => void
): TreeDataNode[] {
  return nodes.map(node => {
    const isDisabled = isNodeDisabled(node);
    const nodeKey = node.key;
    const isInherited = inheritedRoleIds.some((key) => String(key) === String(nodeKey));
    const inheritedRoleSource = inheritedRoleSourceMap[String(nodeKey)] || '';
    const isExplicitlySelected = selectedKeys.some((key) => String(key) === String(nodeKey));
    const isPersonalRole = personalRoleIds.some((key) => String(key) === String(nodeKey));
    const isOrgRole = isExplicitlySelected && (forceOrganizationRole || isDisabled || organizationRoleIds.some((key) => String(key) === String(nodeKey)));
    const organizationRoleSource = organizationRoleSourceMap[String(nodeKey)] || '';
    const isLeafNode = !node.children || node.children.length === 0;
    const canDelete = forceOrganizationRole ? isExplicitlySelected : isPersonalRole;

    return {
      ...node,
      title: (
        <div className="flex justify-between items-center w-full">
          <div className="flex items-center gap-2">
            <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
            {isLeafNode && isInherited && (
              <Tooltip title={`${t('system.role.inheritedFrom')}：${inheritedRoleSource}`}>
                <Tag className='font-mini' color="green">
                  {t('system.role.inheritedRole')}
                </Tag>
              </Tooltip>
            )}
            {isLeafNode && isOrgRole && (
              <Tooltip title={organizationRoleSource ? `${t('system.data.group')}：${organizationRoleSource}` : undefined}>
                <Tag className='font-mini' color="orange">
                  {t('system.role.organizationRole')}
                </Tag>
              </Tooltip>
            )}
            {isLeafNode && isPersonalRole && (
              <Tag className='font-mini' color="blue">
                {t('system.role.personalRole')}
              </Tag>
            )}
          </div>
          {canDelete && (
            <DeleteOutlined
              className="cursor-pointer text-(--color-text-4)"
              onClick={e => {
                e.stopPropagation();
                if (forceOrganizationRole) {
                  const keysToRemove = getDeletableSubtreeKeys(node, organizationRoleIds);
                  let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                  updated = cleanSelectedKeys(updated, treeData);
                  onRemove(updated);
                  return;
                }

                const keysToRemove = getSubtreeKeys(node);
                const updatedPersonalRoleIds = personalRoleIds.filter(
                  (key) => !keysToRemove.some((removeKey) => String(removeKey) === String(key))
                );
                onRemove(updatedPersonalRoleIds);
              }}
            />
          )}
        </div>
      ),
      children: node.children ? transformRightTreeRole(
        node.children,
        treeData,
        selectedKeys,
        personalRoleIds,
        organizationRoleIds,
        organizationRoleSourceMap,
        inheritedRoleIds,
        inheritedRoleSourceMap,
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
  personalRoleIds,
  organizationRoleIds,
  organizationRoleSourceMap,
  inheritedRoleIds,
  inheritedRoleSourceMap,
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
      personalRoleIds,
      organizationRoleIds,
      organizationRoleSourceMap,
      inheritedRoleIds,
      inheritedRoleSourceMap,
      forceOrganizationRole,
      t,
      onChange
    );
  }, [filteredRightData, treeData, selectedKeys, personalRoleIds, onChange, organizationRoleIds, organizationRoleSourceMap, inheritedRoleIds, inheritedRoleSourceMap, mode, onPermissionSetting, forceOrganizationRole, t]);

  return (
    <TransferTreePanel
      searchPlaceholder={t('common.search')}
      searchValue={rightSearchValue}
      onSearchChange={onSearchChange}
      maxHeight={250}
    >
        <Tree
          blockNode
          selectable={false}
          expandedKeys={rightExpandedKeys}
          onExpand={(keys) => onExpandedKeysChange(keys)}
          treeData={transformedData}
          disabled={disabled || loading}
        />
    </TransferTreePanel>
  );
};

export default TransferRightTree;
