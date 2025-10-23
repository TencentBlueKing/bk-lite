import React, { useState, useMemo, useCallback } from 'react';
import { Transfer, Tree, Spin, Tag, Checkbox } from 'antd';
import { DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import PermissionModal from './permissionModal';

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

interface NodeHandlers {
  onPermissionSetting: (node: TreeDataNode, e: React.MouseEvent) => void;
  onRemove: (newKeys: number[]) => void;
}

export const flattenRoleData = (nodes: TreeDataNode[]): { key: number; title: string }[] => {
  return nodes?.reduce<{ key: number; title: string }[]>((acc, node) => {
    if (node.selectable) {
      acc.push({ key: node.key as number, title: node.title as string });
    }
    if (node.children) {
      acc = acc.concat(flattenRoleData(node.children));
    }
    return acc;
  }, []);
};

const filterTreeData = (nodes: TreeDataNode[], selectedKeys: number[]): TreeDataNode[] => {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    const newNode = { ...node };
    if (node.children) {
      const filtered = filterTreeData(node.children, selectedKeys);
      if (filtered.length > 0) {
        newNode.children = filtered;
        acc.push(newNode);
      } else if (selectedKeys.includes(node.key as number)) {
        acc.push(newNode);
      }
    } else if (selectedKeys.includes(node.key as number)) {
      acc.push(newNode);
    }
    return acc;
  }, []);
};

const getSubtreeKeys = (node: TreeDataNode): number[] => {
  const keys = [node.key as number];
  if (node.children && node.children.length > 0) {
    node.children.forEach(child => {
      keys.push(...getSubtreeKeys(child));
    });
  }
  return keys;
};

const cleanSelectedKeys = (
  selected: number[],
  nodes: TreeDataNode[]
): number[] => {
  let result = [...selected];
  nodes.forEach(node => {
    if (!node.selectable && node.children) {
      const childSelectable = flattenRoleData(node.children).map(item => Number(item.key));
      if (result.includes(node.key as number)) {
        if (!childSelectable.every(childKey => result.includes(childKey))) {
          result = result.filter(key => key !== node.key);
        }
      }
      result = cleanSelectedKeys(result, node.children);
    }
  });
  return result;
};

const isFullySelected = (node: TreeDataNode, selectedKeys: number[]): boolean => {
  if (node.children && node.children.length > 0) {
    return node.children.every(child => isFullySelected(child, selectedKeys));
  }
  return selectedKeys.includes(node.key as number);
};

const getAllKeys = (nodes: TreeDataNode[]): number[] => {
  return nodes.reduce<number[]>((acc, node) => {
    acc.push(node.key as number);
    if (node.children) {
      acc.push(...getAllKeys(node.children));
    }
    return acc;
  }, []);
};

const isNodeDisabled = (node: TreeDataNode): boolean => {
  return node.disabled === true;
};

// 新增：当 mode 为 "group" 时，生成右侧树的节点，只保留全选节点
const transformRightTreeGroup = (
  nodes: TreeDataNode[],
  selectedKeys: number[],
  handlers: NodeHandlers
): TreeDataNode[] => {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    if (node.children && node.children.length > 0) {
      const transformedChildren = transformRightTreeGroup(node.children, selectedKeys, handlers);
      if (isFullySelected(node, selectedKeys)) {
        // 当所有子节点都选中时，显示父级分组节点
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
                    updated = cleanSelectedKeys(updated, nodes);
                    handlers.onRemove(updated);
                  }}
                />
              </div>
            </div>
          ),
          children: transformedChildren
        });
      } else {
        // 如果父节点不完全选中，则不显示父节点，只返回选中的子节点
        acc.push(...transformedChildren);
      }
    } else {
      if (selectedKeys.includes(node.key as number)) {
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
                    updated = cleanSelectedKeys(updated, nodes);
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
};

// 修改：增加 forceOrganizationRole 参数和禁用角色处理
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const transformRightTree = (
  nodes: TreeDataNode[],
  treeData: TreeDataNode[],
  selectedKeys: number[],
  onRemove: (newKeys: number[]) => void,
  t: (key: string) => string,
  onPermissionSetting?: (node: TreeDataNode, e: React.MouseEvent) => void,
  mode?: 'group',
  forceOrganizationRole?: boolean
): TreeDataNode[] => {
  if (mode === 'group') {
    // 使用完整树数据生成全选的分组模式
    return transformRightTreeGroup(treeData, selectedKeys, { onPermissionSetting: onPermissionSetting || (() => {}), onRemove });
  }

  return nodes.map(node => {
    const isDisabled = isNodeDisabled(node);
    const isOrgRole = forceOrganizationRole || isDisabled;

    return {
      ...node,
      title: (
        <div className="flex justify-between items-center w-full">
          <div className="flex items-center gap-2">
            <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
            {isOrgRole && (
              <Tag className='font-mini' color="orange">
                {t('system.role.organizationRole')}
              </Tag>
            )}
            {!isOrgRole && (
              <Tag className='font-mini' color="blue">
                {t('system.role.personalRole')}
              </Tag>
            )}
          </div>
          {!isOrgRole && (
            <DeleteOutlined
              className="cursor-pointer text-[var(--color-text-4)]"
              onClick={e => {
                e.stopPropagation();
                const keysToRemove = getSubtreeKeys(node);
                let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                updated = cleanSelectedKeys(updated, treeData);
                onRemove(updated);
              }}
            />
          )}
        </div>
      ),
      children: node.children ? transformRightTree(node.children, treeData, selectedKeys, onRemove, t, onPermissionSetting, mode, forceOrganizationRole) : []
    };
  });
};

// 处理左侧树数据，禁用组织角色
const processLeftTreeData = (nodes: TreeDataNode[], organizationRoleIds: number[]): TreeDataNode[] => {
  return nodes.map(node => ({
    ...node,
    disabled: node.disabled || organizationRoleIds.includes(node.key as number),
    children: node.children ? processLeftTreeData(node.children, organizationRoleIds) : undefined
  }));
};

// 新增：处理左侧树数据，添加"全部子组织"复选框
const renderTreeNodeTitle = (
  node: TreeDataNode,
  selectedKeys: number[],
  enableSubGroupSelect: boolean,
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void,
  t: (key: string) => string
): React.ReactNode => {
  const hasChildren = node.children && node.children.length > 0;

  const nodeTitle = typeof node.title === 'function' ? node.title(node) : node.title;

  if (!hasChildren || !enableSubGroupSelect) {
    return nodeTitle;
  }

  // 修复：使用递归检查所有子孙节点是否全部选中
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
};

// 新增：转换左侧树数据，添加自定义标题
const transformLeftTreeData = (
  nodes: TreeDataNode[],
  selectedKeys: number[],
  enableSubGroupSelect: boolean,
  onSubGroupToggle: (node: TreeDataNode, includeAll: boolean) => void,
  t: (key: string) => string,
  organizationRoleIds: number[]
): TreeDataNode[] => {
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
};

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

  // 新增：处理"全部子组织"复选框切换
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

  // 处理左侧树数据，禁用组织角色
  const leftTreeData = useMemo(() => {
    if (mode === 'group' && enableSubGroupSelect) {
      return transformLeftTreeData(
        treeData,
        selectedKeys,
        enableSubGroupSelect,
        handleSubGroupToggle,
        t,
        organizationRoleIds
      );
    }
    return processLeftTreeData(treeData, organizationRoleIds);
  }, [treeData, selectedKeys, enableSubGroupSelect, handleSubGroupToggle, t, mode, organizationRoleIds]);

  const flattenedRoleData = useMemo(() => flattenRoleData(leftTreeData), [leftTreeData]);
  const leftExpandedKeys = useMemo(() => getAllKeys(leftTreeData), [leftTreeData]);
  const filteredRightData = useMemo(() => filterTreeData(treeData, selectedKeys), [treeData, selectedKeys]);

  const handlePermissionSetting = (node: TreeDataNode, e: React.MouseEvent) => {
    e.stopPropagation();
    setCurrentNode(node);
    const nodeKey = node.key as number;
    const rules = groupRules[nodeKey] || {};
    setCurrentRules(rules);
    setIsPermissionModalVisible(true);
  };

  const handlePermissionOk = (values: any) => {
    if (!currentNode || !onChangeRule) return;

    // 构建应用权限映射对象，保持应用名和权限值的对应关系
    const appPermissionMap: { [app: string]: number } = {};
    values?.permissions?.forEach((permission: any) => {
      if (permission.permission !== 0) {
        appPermissionMap[permission.app] = permission.permission;
      }
    });

    const nodeKey = currentNode.key as number;

    onChangeRule(nodeKey, appPermissionMap);
    setIsPermissionModalVisible(false);
  };

  // 创建一个新的 transformRightTree 函数，使用 organizationRoleIds 来判断组织角色
  const transformRightTreeWithOrgRoles = (
    nodes: TreeDataNode[],
    treeData: TreeDataNode[],
    selectedKeys: number[],
    onRemove: (newKeys: number[]) => void,
    organizationRoleIds: number[]
  ): TreeDataNode[] => {
    if (mode === 'group') {
      return transformRightTreeGroup(treeData, selectedKeys, {
        onPermissionSetting: onChangeRule ? handlePermissionSetting : () => {},
        onRemove
      });
    }

    return nodes.map(node => {
      const isDisabled = isNodeDisabled(node);
      const isOrgRole = forceOrganizationRole || isDisabled || organizationRoleIds.includes(node.key as number);
      const isLeafNode = !node.children || node.children.length === 0;

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
            {!isOrgRole && (
              <DeleteOutlined
                className="cursor-pointer text-[var(--color-text-4)]"
                onClick={e => {
                  e.stopPropagation();
                  const keysToRemove = getSubtreeKeys(node);
                  let updated = selectedKeys.filter(key => !keysToRemove.includes(key));
                  updated = cleanSelectedKeys(updated, treeData);
                  onRemove(updated);
                }}
              />
            )}
          </div>
        ),
        children: node.children ? transformRightTreeWithOrgRoles(node.children, treeData, selectedKeys, onRemove, organizationRoleIds) : []
      };
    });
  };

  const rightTransformedData = useMemo(() =>
    transformRightTreeWithOrgRoles(
      filteredRightData,
      treeData,
      selectedKeys,
      onChange,
      organizationRoleIds
    ), [filteredRightData, treeData, selectedKeys, onChange, organizationRoleIds, mode, onChangeRule, forceOrganizationRole]
  );

  const rightExpandedKeys = useMemo(() =>
    getAllKeys(rightTransformedData), [rightTransformedData]
  );

  const transferDataSource = useMemo(() => {
    if (mode === 'group') {
      const getAllLeafNodes = (nodes: TreeDataNode[]): { key: number; title: string }[] => {
        return nodes.reduce<{ key: number; title: string }[]>((acc, node) => {
          if (!node.children || node.children.length === 0) {
            acc.push({ key: node.key as number, title: node.title as string });
          } else {
            acc = acc.concat(getAllLeafNodes(node.children));
          }
          return acc;
        }, []);
      };

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
                <div className="p-1 max-h-[250px] overflow-auto">
                  <Tree
                    blockNode
                    checkable
                    selectable={false}
                    checkStrictly={mode === 'group'}
                    expandedKeys={leftExpandedKeys}
                    checkedKeys={mode === 'group' ? { checked: selectedKeys, halfChecked: [] } : selectedKeys}
                    treeData={leftTreeData}
                    disabled={disabled || loading}
                    onCheck={(checkedKeys, info) => {
                      if (!disabled && !loading) {
                        // group 模式下使用 checked 数组，role 模式直接使用 checkedKeys
                        // const actualCheckedKeys = mode === 'group'
                        //   ? (checkedKeys as { checked: React.Key[]; halfChecked: React.Key[] }).checked
                        //   : (checkedKeys as React.Key[]);

                        // 过滤掉禁用的节点（包括组织角色）
                        const validCheckedNodes = info.checkedNodes.filter((node: any) => !isNodeDisabled(node) && !organizationRoleIds.includes(node.key));
                        const newKeys = validCheckedNodes.map((node: any) => node.key);

                        // 保留原有的组织角色（被禁用的节点）
                        const existingOrgRoles = selectedKeys.filter(key => organizationRoleIds.includes(key));
                        const finalKeys = [...new Set([...newKeys, ...existingOrgRoles])];

                        onChange(finalKeys);
                      }
                    }}
                  />
                </div>
              );
            } else if (direction === 'right') {
              return (
                <div className="w-full p-1 max-h-[250px] overflow-auto">
                  <Tree
                    blockNode
                    selectable={false}
                    expandedKeys={rightExpandedKeys}
                    treeData={rightTransformedData}
                    disabled={disabled || loading}
                  />
                </div>
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
