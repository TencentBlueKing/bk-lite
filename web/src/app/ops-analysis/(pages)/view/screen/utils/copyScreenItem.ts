import type { Dispatch, SetStateAction } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import { copyScreenWidget } from '@/app/ops-analysis/utils/widgetCopy';

export const createScreenCopyItemHandler = ({
  setDraftViewSets,
  setSelectedItemId,
  rebuildFilters,
  createId = uuidv4,
}: {
  setDraftViewSets: Dispatch<SetStateAction<ScreenViewSets>>;
  setSelectedItemId: Dispatch<SetStateAction<string | null>>;
  rebuildFilters: (viewSets: ScreenViewSets) => ScreenViewSets;
  createId?: () => string;
}) => {
  return (itemId: string) => {
    const copiedItemId = createId();
    setDraftViewSets((current) => {
      const copied = copyScreenWidget(current, itemId, {
        createId: () => copiedItemId,
      });
      if (!copied) {
        return current;
      }
      return rebuildFilters(copied.viewSets);
    });
    setSelectedItemId(copiedItemId);
  };
};
