import type { ViewConfigItem } from '@/app/ops-analysis/types/dashBoard';

/**
 * Remount key for Card List settings so local optional-group UI state
 * does not leak across edit targets. Must tolerate create/close paths where
 * the parent still mounts ViewConfig with a missing item.
 */
export const resolveCardListSettingsRemountKey = (
  item?: ViewConfigItem | null,
): string => {
  if (!item) {
    return 'new-card-list';
  }
  if ('i' in item && typeof item.i === 'string') {
    const widgetId = item.i.trim();
    if (widgetId) {
      return widgetId;
    }
  }
  return 'new-card-list';
};
