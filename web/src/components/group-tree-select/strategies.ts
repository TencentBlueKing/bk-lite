/**
 * GroupTreeSelect 选择策略实现
 * 实现策略模式以支持不同的选择场景
 */

import type { TreeSelectProps } from 'antd';
import type { SelectionStrategy, TreeNode, SelectionMode } from './types';

/**
 * 默认选择策略
 * 保持现有的 treeCheckStrictly 行为，向后兼容
 */
class DefaultStrategy implements SelectionStrategy {
  handleNodeCheck(
    checkedKeys: number[],
    node: TreeNode,
    checked: boolean
  ): number[] {
    if (checked) {
      // 添加节点到选中列表（不联动父子）
      return [...checkedKeys, node.key];
    } else {
      // 从选中列表移除节点
      return checkedKeys.filter(key => key !== node.key);
    }
  }

  transformTreeData(treeData: TreeNode[]): TreeNode[] {
    // 默认策略不对树数据做任何转换
    return treeData;
  }

  getTreeSelectProps(): Partial<TreeSelectProps> {
    return {
      treeCheckStrictly: true, // 不联动父子节点
      showCheckedStrategy: 'SHOW_ALL', // 显示所有选中节点
    };
  }
}

/**
 * 数据归属选择策略
 * 支持独立选择，不联动父子节点
 * 适用于业务数据创建场景（如CMDB模型、应用、知识库等）
 */
class OwnershipStrategy implements SelectionStrategy {
  handleNodeCheck(
    checkedKeys: number[],
    node: TreeNode,
    checked: boolean
  ): number[] {
    if (checked) {
      // 仅选中当前节点，不联动父子
      if (!checkedKeys.includes(node.key)) {
        return [...checkedKeys, node.key];
      }
      return checkedKeys;
    } else {
      // 取消选中当前节点
      return checkedKeys.filter(key => key !== node.key);
    }
  }

  transformTreeData(treeData: TreeNode[]): TreeNode[] {
    // 可以在这里添加自定义渲染，如添加标签等
    // 目前保持原样
    return treeData;
  }

  getTreeSelectProps(): Partial<TreeSelectProps> {
    return {
      treeCheckStrictly: true, // 独立选择，不联动
      showCheckedStrategy: 'SHOW_ALL', // 显示所有选中节点
    };
  }
}

/**
 * 策略工厂
 * 根据模式创建对应的策略实例
 * @param mode 选择模式
 * @returns 策略实例
 */
export const createStrategy = (mode: SelectionMode = 'ownership'): SelectionStrategy => {
  switch (mode) {
    case 'default':
      return new DefaultStrategy();
    case 'ownership':
    default:
      return new OwnershipStrategy();
  }
};

/**
 * 导出策略类供测试使用
 */
export { DefaultStrategy, OwnershipStrategy };
