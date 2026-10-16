/**
 * React 19 在 commitDeletion 里按 fiber 记下的父节点调用 removeChild。
 * antd Portal（Tooltip / Popover / Dropdown / Select / DatePicker / Drawer）
 * 走 @rc-component/trigger 的 useAlign：测量时把占位节点插进 popup 的父节点，
 * 结束时用「当时的 popup.parentElement」再 removeChild。
 * 主机分类页签只挂当前 pane（category-layout renderPane），切换时整棵
 * Tooltip、Popover、表头排序提示和图表一起卸载；占位节点或 cssVar 样式
 * 若已被移走，第二次 removeChild 会抛
 * NotFoundError: The node to be removed is not a child of this node.
 * Next 16 Turbopack 开发态会把这次提交阶段异常显示成运行时错误。
 * 父节点已经不是该节点的父级时，卸载视为完成，不再抛。
 */
const PATCH_FLAG = '__bkLiteAntdPortalCleanup';

type PatchedNode = Node & { [PATCH_FLAG]?: boolean };

export function installAntdPortalUnmountGuard(): void {
  if (typeof window === 'undefined' || typeof Node === 'undefined') return;
  const proto = Node.prototype as PatchedNode;
  if (proto[PATCH_FLAG]) return;
  proto[PATCH_FLAG] = true;

  const removeChild = proto.removeChild;
  proto.removeChild = function removeChildIfStillChild<T extends Node>(this: Node, child: T): T {
    if (child.parentNode !== this) return child;
    return removeChild.call(this, child) as T;
  };

  const insertBefore = proto.insertBefore;
  proto.insertBefore = function insertBeforeIfStillChild<T extends Node>(
    this: Node,
    node: T,
    child: Node | null,
  ): T {
    if (child && child.parentNode !== this) return node;
    return insertBefore.call(this, node, child) as T;
  };
}

installAntdPortalUnmountGuard();
