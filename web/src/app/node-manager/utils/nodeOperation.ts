import type { TableDataItem } from '../types';

export const isControllerOperationDisabled = (selectedNodes: TableDataItem[]) => {
  if (!selectedNodes.length) return true;

  const operatingSystems = selectedNodes.map((node) => node.operating_system);
  const uniqueOS = [...new Set(operatingSystems)];

  return uniqueOS.length !== 1 || operatingSystems.includes('windows');
};
