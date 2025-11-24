/**
 * GroupTreeSelect 组件类型定义
 * 支持权限授予和数据归属两种场景
 */

/**
 * 选择模式类型
 * - ownership: 数据归属模式（默认，支持独立选择，不联动父子）
 * - default: 默认模式（特殊场景使用，保持向后兼容）
 */
export type SelectionMode = 'ownership' | 'default';

/**
 * 树节点接口
 */
export interface TreeNode {
  key: number;
  value?: number;
  title: string;
  disabled?: boolean;
  children?: TreeNode[];
  [key: string]: any;
}

/**
 * GroupTreeSelect 组件 Props
 */
export interface GroupTreeSelectProps {
  /**
   * 当前选中的值
   */
  value?: number | number[];

  /**
   * 值变化回调
   */
  onChange?: (value: number | number[] | undefined) => void;

  /**
   * 占位文本
   */
  placeholder?: string;

  /**
   * 是否支持多选
   * @default true
   */
  multiple?: boolean;

  /**
   * 是否禁用
   * @default false
   */
  disabled?: boolean;

  /**
   * 样式
   */
  style?: React.CSSProperties;

  /**
   * 选择模式
   * @default 'ownership'
   */
  mode?: SelectionMode;

  /**
   * 面板高度
   * @default 300
   */
  height?: number;

  /**
   * 是否显示搜索框
   * @default false
   */
  showSearch?: boolean;
}

/**
 * 选择策略接口
 * 用于实现不同的选择逻辑
 */
export interface SelectionStrategy {
  /**
   * 处理节点勾选逻辑
   * @param checkedKeys 当前已选中的节点ID列表
   * @param node 被操作的节点
   * @param checked 是否选中
   * @returns 新的选中节点ID列表
   */
  handleNodeCheck(
    checkedKeys: number[],
    node: TreeNode,
    checked: boolean
  ): number[];

  /**
   * 转换树数据（可添加自定义渲染）
   * @param treeData 原始树数据
   * @returns 转换后的树数据
   */
  transformTreeData(treeData: TreeNode[]): TreeNode[];
}

/**
 * 策略工厂函数类型
 */
export type StrategyFactory = (mode: SelectionMode) => SelectionStrategy;
