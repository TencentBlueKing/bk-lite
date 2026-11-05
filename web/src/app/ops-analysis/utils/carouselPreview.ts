/** 编辑态不能开始预览轮播。查看态可以。 */
export const canStartCarouselPreview = (editing: boolean): boolean => !editing;

export interface CarouselEditorOpenRequest {
  id: string;
  nonce: number;
}

/** 只在目标列表自己加载完成、条目为空且可编辑时打开抽屉。旧列表不能消费这次信号。 */
export const shouldAutoOpenCarouselEditor = (input: {
  request: CarouselEditorOpenRequest | null;
  appliedNonce: number;
  loadedId: string | null;
  loading: boolean;
  itemCount: number;
  canEdit: boolean;
}): boolean => {
  const { request } = input;
  if (!request || request.nonce === 0 || input.appliedNonce === request.nonce) {
    return false;
  }
  if (input.loading || !input.canEdit || input.loadedId !== request.id) {
    return false;
  }
  return input.itemCount === 0;
};

/**
 * 当前预览项被删掉时，落到原来的下一张；已经是最后一张则落到上一张。
 * 删的是别的项时，仍停在同一张画布上。
 */
export const relocatePreviewIndex = (
  previousIndex: number,
  removedIndexes: readonly number[],
  nextLength: number,
): number => {
  if (nextLength <= 0) {
    return -1;
  }
  const removedBefore = removedIndexes.filter((index) => index < previousIndex).length;
  const shifted = previousIndex - removedBefore;
  return Math.min(Math.max(shifted, 0), nextLength - 1);
};

export const relocatePreviewIndexByKeys = (
  previousKeys: readonly string[],
  previousIndex: number,
  nextKeys: readonly string[],
): number => {
  if (nextKeys.length === 0) {
    return -1;
  }
  const key = previousKeys[previousIndex];
  if (key) {
    const found = nextKeys.indexOf(key);
    if (found >= 0) {
      return found;
    }
  }
  if (previousKeys.length === 0) {
    return 0;
  }
  const removed = previousKeys.flatMap((item, index) => (nextKeys.includes(item) ? [] : [index]));
  return relocatePreviewIndex(previousIndex, removed, nextKeys.length);
};

/** 缩略条和上一张/下一张按完整列表相邻移动，失效项也算一张。 */
export const manualPreviewStep = (length: number, index: number, direction: 1 | -1): number => {
  if (length <= 0) {
    return -1;
  }
  if (index < 0) {
    return direction > 0 ? 0 : length - 1;
  }
  return (index + direction + length) % length;
};
