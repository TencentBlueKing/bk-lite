import type { WidgetInteractionLink } from '@/app/ops-analysis/types/dashBoard';
import type { ScreenTextItem } from '@/app/ops-analysis/types/screen';
import { normalizeInteractionLink } from '@/app/ops-analysis/utils/interactionLink';

/** 文本项只保留标题链接。选无、数据链接或空 URL 都变成不保存。 */
export const persistScreenTextInteraction = (
  link: {
    kind?: string;
    name?: string;
    url?: string;
    openMode?: WidgetInteractionLink['openMode'];
  } | null | undefined,
): WidgetInteractionLink | undefined => {
  if (!link || link.kind !== 'title') return undefined;
  return normalizeInteractionLink({
    kind: 'title',
    name: link.name,
    url: link.url,
    openMode: link.openMode,
  });
};

export const withScreenTextInteraction = (
  item: ScreenTextItem,
  draft: Parameters<typeof persistScreenTextInteraction>[0],
): ScreenTextItem => {
  const interaction = persistScreenTextInteraction(draft);
  if (!interaction) {
    if (item.interaction === undefined) return item;
    const rest = { ...item };
    delete rest.interaction;
    return rest;
  }
  const current = item.interaction;
  if (
    current?.kind === interaction.kind
    && current.name === interaction.name
    && current.url === interaction.url
    && current.openMode === interaction.openMode
  ) {
    return item;
  }
  return { ...item, interaction };
};
