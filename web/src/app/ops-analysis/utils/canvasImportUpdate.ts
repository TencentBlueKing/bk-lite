import { CANVAS_TYPE_REGISTRY, type CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import type { DirItem } from '@/app/ops-analysis/types';

export const canvasImportUpdatePath = (objectType: CanvasType, objectId: number): string => {
  const endpoint = CANVAS_TYPE_REGISTRY[objectType].endpoint;
  return `${endpoint}${objectId}/import-update/`;
};

export const canvasSelectionAfterImportUpdate = (
  item: DirItem,
  result: { name: string; desc?: string },
): DirItem => ({
  ...item,
  name: result.name,
  desc: result.desc ?? item.desc ?? '',
});
