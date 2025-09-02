/**
 * 数据树构建工具函数
 * 用于将数据源返回的数据结构转换为 Tree 组件所需的树形结构
 */

/**
 * 构建树形数据结构
 * @param obj 原始数据对象或数组
 * @returns 树形节点数组
 */
export const buildTreeData = (obj: any): any[] => {
  if (typeof obj !== 'object' || obj === null) {
    return [];
  }

  const treeNodes: any[] = [];

  // 如果是数组，检查第一个元素
  if (Array.isArray(obj) && obj.length > 0) {
    const firstItem = obj[0];

    if (
      firstItem &&
      typeof firstItem === 'object' &&
      firstItem.namespace_id &&
      firstItem.data
    ) {
      // 处理包含 namespace_id 和 data 的特殊数据结构
      treeNodes.push({
        title: 'namespace_id',
        key: 'namespace_id',
        value: 'namespace_id',
        isLeaf: true,
      });

      // 添加 data 节点
      const dataChildren: any[] = [];
      if (Array.isArray(firstItem.data) && firstItem.data.length > 0) {
        const dataItem = firstItem.data[0];
        if (typeof dataItem === 'object' && dataItem !== null) {
          Object.keys(dataItem).forEach((key) => {
            dataChildren.push({
              title: key,
              key: `data.${key}`,
              value: `data.${key}`,
              isLeaf: true,
            });
          });
        }
      } else if (
        typeof firstItem.data === 'object' &&
        firstItem.data !== null
      ) {
        Object.keys(firstItem.data).forEach((key) => {
          dataChildren.push({
            title: key,
            key: `data.${key}`,
            value: `data.${key}`,
            isLeaf: true,
          });
        });
      }

      if (dataChildren.length > 0) {
        treeNodes.push({
          title: 'data',
          key: 'data',
          children: dataChildren,
        });
      }

      return treeNodes;
    }

    // 普通数组处理
    const firstElement = firstItem;
    if (typeof firstElement === 'object' && firstElement !== null) {
      return buildTreeData(firstElement);
    } else {
      return [
        {
          title: '数据值',
          key: 'value',
          value: 'value',
          isLeaf: true,
        },
      ];
    }
  }

  // 普通对象处理
  Object.keys(obj).forEach((key) => {
    const value = obj[key];

    if (
      typeof value === 'object' &&
      value !== null &&
      !Array.isArray(value)
    ) {
      const children = buildTreeData(value);
      if (children.length > 0) {
        treeNodes.push({
          title: key,
          key: key,
          children: children.map((child) => ({
            ...child,
            key: `${key}.${child.key}`,
            value: `${key}.${child.value || child.key}`,
          })),
        });
      }
    } else {
      treeNodes.push({
        title: key,
        key: key,
        value: key,
        isLeaf: true,
      });
    }
  });

  return treeNodes;
};
