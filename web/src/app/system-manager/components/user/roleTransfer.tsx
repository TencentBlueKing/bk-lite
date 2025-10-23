import React, { useState, useMemo } from 'react';
import { Transfer, Tree, Spin } from 'antd';
import { DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
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
}

// 增加事件处理函数接口
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

// 修改：增加 mode 参数，默认为普通模式
const transformRightTree = (
  nodes: TreeDataNode[],
  treeData: TreeDataNode[],
  selectedKeys: number[],
  onRemove: (newKeys: number[]) => void,
  onPermissionSetting?: (node: TreeDataNode, e: React.MouseEvent) => void,
  mode?: 'group'
): TreeDataNode[] => {
  if (mode === 'group') {
    // 使用完整树数据生成全选的分组模式
    return transformRightTreeGroup(treeData, selectedKeys, { onPermissionSetting: onPermissionSetting || (() => {}), onRemove });
  }
  return nodes.map(node => ({
    ...node,
    title: (
      <div className="flex justify-between items-center w-full">
        <span>{typeof node.title === 'function' ? node.title(node) : node.title}</span>
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
      </div>
    ),
    children: node.children ? transformRightTree(node.children, treeData, selectedKeys, onRemove) : []
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
  loading = false
}) => {
  const [isPermissionModalVisible, setIsPermissionModalVisible] = useState<boolean>(false);
  const [currentNode, setCurrentNode] = useState<TreeDataNode | null>(null);
  const [currentRules, setCurrentRules] = useState<{ [app: string]: number }>({});

  const flattenedRoleData = useMemo(() => flattenRoleData(treeData), [treeData]);
  const leftExpandedKeys = useMemo(() => getAllKeys(treeData), [treeData]);
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

  const rightTransformedData = useMemo(() =>
    transformRightTree(
      filteredRightData,
      treeData,
      selectedKeys,
      onChange,
      mode === 'group' && onChangeRule ? handlePermissionSetting : undefined,
      mode === 'group' ? 'group' : undefined
    ), [filteredRightData, treeData, selectedKeys, onChange, mode, onChangeRule]
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
                    expandedKeys={leftExpandedKeys}
                    checkedKeys={selectedKeys}
                    treeData={treeData}
                    disabled={disabled || loading}
                    onCheck={(checkedKeys, info) => {
                      if (!disabled && !loading) {
                        const newKeys = info.checkedNodes.map((node: any) => node.key);
                        onChange(newKeys);
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
