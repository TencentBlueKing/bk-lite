import type { Dispatch, SetStateAction } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ScreenItem, ScreenViewSets } from '@/app/ops-analysis/types/screen';
import {
  copyScreenWidget,
  type CopyMessage,
} from '@/app/ops-analysis/utils/widgetCopy';
import {
  isScreenClockItem,
  isScreenDecorationItem,
  isScreenShapeItem,
  isScreenTextItem,
  isScreenTitleFrameItem,
  isScreenWidgetItem,
} from './screenItems';

const SCREEN_COPY_OFFSET = 48;

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const isCopyableScreenChrome = (item: ScreenItem) =>
  isScreenTextItem(item) ||
  isScreenClockItem(item) ||
  isScreenTitleFrameItem(item) ||
  isScreenDecorationItem(item) ||
  isScreenShapeItem(item);

export const copyScreenChromeItem = (
  viewSets: ScreenViewSets,
  sourceId: string,
  options?: { createId?: () => string },
): { viewSets: ScreenViewSets; selectedItemId: string } | null => {
  const source = viewSets.items.find((item) => item.id === sourceId);
  if (!source || isScreenWidgetItem(source) || !isCopyableScreenChrome(source)) {
    return null;
  }
  const cloned = JSON.parse(JSON.stringify(source)) as ScreenItem;
  const maxZ = viewSets.items.reduce(
    (max, item) => Math.max(max, item.zIndex || 0),
    0,
  );
  const copied: ScreenItem = {
    ...cloned,
    id: (options?.createId ?? uuidv4)(),
    x: clamp(
      source.x + SCREEN_COPY_OFFSET,
      0,
      Math.max(0, viewSets.viewport.width - source.w),
    ),
    y: clamp(
      source.y + SCREEN_COPY_OFFSET,
      0,
      Math.max(0, viewSets.viewport.height - source.h),
    ),
    zIndex: maxZ + 1,
  };
  return {
    viewSets: {
      ...viewSets,
      items: [...viewSets.items, copied],
    },
    selectedItemId: copied.id,
  };
};

export const createScreenCopyItemHandler = ({
  getDraftViewSets,
  setDraftViewSets,
  setSelectedItemId,
  rebuildFilters,
  createId = uuidv4,
  t,
}: {
  getDraftViewSets: () => ScreenViewSets;
  setDraftViewSets: Dispatch<SetStateAction<ScreenViewSets>>;
  setSelectedItemId: Dispatch<SetStateAction<string | null>>;
  rebuildFilters: (viewSets: ScreenViewSets) => ScreenViewSets;
  createId?: () => string;
  t?: CopyMessage;
}) => {
  return (itemId: string) => {
    const copiedItemId = createId();
    const tryCopy = (current: ScreenViewSets) => {
      const copied =
        copyScreenWidget(current, itemId, {
          createId: () => copiedItemId,
          t,
        }) ??
        copyScreenChromeItem(current, itemId, {
          createId: () => copiedItemId,
        });
      if (!copied) {
        return null;
      }
      return rebuildFilters(copied.viewSets);
    };

    const preview = tryCopy(getDraftViewSets());
    if (!preview) {
      return;
    }

    let applied: ScreenViewSets | null | undefined;
    setDraftViewSets((current) => {
      applied = tryCopy(current);
      return applied ?? current;
    });

    const landed = applied === undefined ? preview : applied;
    if (landed) {
      setSelectedItemId(copiedItemId);
    }
  };
};
