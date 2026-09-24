import type { Dispatch, SetStateAction } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import {
  copyScreenWidget,
  type CopyMessage,
} from '@/app/ops-analysis/utils/widgetCopy';

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
      const copied = copyScreenWidget(current, itemId, {
        createId: () => copiedItemId,
        t,
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
