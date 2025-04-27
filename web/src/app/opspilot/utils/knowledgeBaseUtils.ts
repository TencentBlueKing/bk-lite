export const defaultIconTypes = ['zhishiku', 'zhishiku-red', 'zhishiku-blue', 'zhishiku-yellow', 'zhishiku-green'];

/**
 * 根据索引获取图标类型。
 * @param index 索引
 * @param iconTypes 图标类型数组
 * @returns 对应的图标类型
 */
export const getIconTypeByIndex = (index: number, iconTypes: string[] = defaultIconTypes): string =>
  iconTypes[index % iconTypes.length] || 'zhishiku';
