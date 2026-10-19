export interface InteractionSampleTicket {
  widgetId: string;
  sequence: number;
}

export const nextInteractionSampleTicket = (
  current: InteractionSampleTicket,
  widgetId: string,
): InteractionSampleTicket => ({
  widgetId,
  sequence: current.sequence + 1,
});

export const isCurrentInteractionSample = (
  current: InteractionSampleTicket,
  ticket: InteractionSampleTicket,
) => current.widgetId === ticket.widgetId && current.sequence === ticket.sequence;

/** 预览回写必须带着这次样本请求的票据；切换组件后旧预览不能再写。 */
export const acceptPreviewRawWrite = (
  current: InteractionSampleTicket,
  ticket: InteractionSampleTicket | undefined,
): ticket is InteractionSampleTicket => (
  Boolean(ticket) && isCurrentInteractionSample(current, ticket)
);

/** 这次请求失败就把 key 清掉，下次打开交互页才能重试。过期票据不能清掉后来的 key。 */
export const clearSampleKeyOnFetchFailure = (
  current: InteractionSampleTicket,
  ticket: InteractionSampleTicket,
  fetchedKey: string,
): string => (
  isCurrentInteractionSample(current, ticket) ? '' : fetchedKey
);

export type InteractionSamplePlan =
  | { type: 'use-rendered'; data: unknown }
  | { type: 'fetch'; sampleKey: string }
  | { type: 'skip' };

/** 画布上已有该组件数据时直接用，不再请求。初始化未完成时也不要用上一个组件的数据源去拉。 */
export const planInteractionSample = (input: {
  open: boolean;
  interactionVisible: boolean;
  hasPreview: boolean;
  widgetId: string;
  settledWidgetId: string | null;
  rendered: unknown;
  sourceId: string | number | null | undefined;
  fetchedKey: string;
}): InteractionSamplePlan => {
  if (!input.open || !input.interactionVisible || input.hasPreview) {
    return { type: 'skip' };
  }
  if (input.rendered != null) {
    return { type: 'use-rendered', data: input.rendered };
  }
  if (input.settledWidgetId !== input.widgetId) {
    return { type: 'skip' };
  }
  if (input.sourceId == null || input.sourceId === '') {
    return { type: 'skip' };
  }
  const sampleKey = `${input.widgetId}:${String(input.sourceId)}`;
  if (input.fetchedKey === sampleKey) {
    return { type: 'skip' };
  }
  return { type: 'fetch', sampleKey };
};
