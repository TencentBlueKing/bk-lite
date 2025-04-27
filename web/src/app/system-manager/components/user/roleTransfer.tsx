import React, { useState, useMemo } from 'react';
import { Transfer, Tree } from 'antd';
import { DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import PermissionModal from './permissionModal';

interface TreeTransferProps {
  treeData: TreeDataNode[];
  selectedKeys: string[];
  groupRules?: { [key: string]: number[] },
  onChange: (newKeys: string[]) => void;
  onChangeRule?: (newKey: string, newRules: number[]) => void;
  mode?: 'group' | 'role'; // 新增：选择模式，默认 'role'
}

export const flattenRoleData = (nodes: TreeDataNode[]): { key: string; title: string }[] => {
  return nodes?.reduce<{ key: string; title: string }[]>((acc, node) => {
    if (node.selectable) {
      acc.push({ key: node.key as string, title: node.title as string });
    }
    if (node.children) {
      acc = acc.concat(flattenRoleData(node.children));
    }
    return acc;
  }, []);
};

const filterTreeData = (nodes: TreeDataNode[], selectedKeys: string[]): TreeDataNode[] => {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    const newNode = { ...node };
    if (node.children) {
      const filtered = filterTreeData(node.children, selectedKeys);
      if (filtered.length > 0) {
        newNode.children = filtered;
        acc.push(newNode);
      } else if (selectedKeys.includes(String(node.key))) {
        acc.push(newNode);
      }
    } else if (selectedKeys.includes(String(node.key))) {
      acc.push(newNode);
    }
    return acc;
  }, []);
};

const getSubtreeKeys = (node: TreeDataNode): string[] => {
  const keys = [String(node.key)];
  if (node.children && node.children.length > 0) {
    node.children.forEach(child => {
      keys.push(...getSubtreeKeys(child));
    });
  }
  return keys;
};

const cleanSelectedKeys = (
  selected: string[],
  nodes: TreeDataNode[]
): string[] => {
  let result = [...selected];
  nodes.forEach(node => {
    if (!node.selectable && node.children) {
      const childSelectable = flattenRoleData(node.children).map(item => item.key);
      if (result.includes(String(node.key))) {
        if (!childSelectable.every(childKey => result.includes(childKey))) {
          result = result.filter(key => key !== String(node.key));
        }
      }
      result = cleanSelectedKeys(result, node.children);
    }
  });
  return result;
};

// 新增：判断节点是否全选（包括子节点）
const isFullySelected = (node: TreeDataNode, selectedKeys: string[]): boolean => {
  if (node.children && node.children.length > 0) {
    return node.children.every(child => isFullySelected(child, selectedKeys));
  }
  return selectedKeys.includes(String(node.key));
};

// 增加事件处理函数接口
interface NodeHandlers {
  onPermissionSetting: (node: TreeDataNode, e: React.MouseEvent) => void;
  onRemove: (newKeys: string[]) => void;
}

// 新增：当 mode 为 "group" 时，生成右侧树的节点，只保留全选节点
const transformRightTreeGroup = (
  nodes: TreeDataNode[],
  selectedKeys: string[],
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
      // 处理叶子节点
      if (selectedKeys.includes(String(node.key))) {
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
  selectedKeys: string[],
  onRemove: (newKeys: string[]) => void,
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

const getAllKeys = (nodes: TreeDataNode[]): string[] => {
  return nodes.reduce<string[]>((acc, node) => {
    acc.push(String(node.key));
    if (node.children) {
      acc.push(...getAllKeys(node.children));
    }
    return acc;
  }, []);
};

const RoleTransfer: React.FC<TreeTransferProps> = ({ treeData, selectedKeys, groupRules = {}, onChange, onChangeRule, mode = 'role' }) => {
  const [isPermissionModalVisible, setIsPermissionModalVisible] = useState<boolean>(false);
  const [currentNode, setCurrentNode] = useState<TreeDataNode | null>(null);
  const [currentRules, setCurrentRules] = useState<number[]>([]);

  // 使用 useMemo 缓存计算，提高性能
  const flattenedRoleData = useMemo(() => flattenRoleData(treeData), [treeData]);
  const leftExpandedKeys = useMemo(() => getAllKeys(treeData), [treeData]);
  const filteredRightData = useMemo(() => filterTreeData(treeData, selectedKeys), [treeData, selectedKeys]);

  const handlePermissionSetting = (node: TreeDataNode, e: React.MouseEvent) => {
    e.stopPropagation();
    setCurrentNode(node);
    const nodeKey = String(node.key);
    const rules = groupRules[nodeKey] || [];
    setCurrentRules(rules);
    setIsPermissionModalVisible(true);
  };

  const handlePermissionOk = (values: any) => {
    if (!currentNode || !onChangeRule) return;

    const filteredPermissions = values?.permissions?.filter((val: any) => val.permission !== 0).map((val: any) => val.permission);
    const nodeKey = String(currentNode.key);

    // 调用外部传入的修改规则的回调
    onChangeRule(nodeKey, filteredPermissions);
    setIsPermissionModalVisible(false);
  };

  // 右侧树数据转换
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

  // 修改 Transfer 的数据源
  const transferDataSource = useMemo(() => {
    if (mode === 'group') {
      // 对于 group 模式，确保包含所有的叶子节点
      const getAllLeafNodes = (nodes: TreeDataNode[]): { key: string; title: string }[] => {
        return nodes.reduce<{ key: string; title: string }[]>((acc, node) => {
          if (!node.children || node.children.length === 0) {
            acc.push({ key: node.key as string, title: node.title as string });
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
      <Transfer
        oneWay
        dataSource={transferDataSource}
        targetKeys={selectedKeys}
        className="tree-transfer"
        render={(item) => item.title}
        showSelectAll={false}
        onChange={(nextTargetKeys) => {
          onChange(nextTargetKeys as string[]);
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
                  onCheck={(checkedKeys, info) => {
                    const newKeys = info.checkedNodes.map((node: any) => node.key);
                    onChange(newKeys);
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
                />
              </div>
            );
          }
        }}
      </Transfer>
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
