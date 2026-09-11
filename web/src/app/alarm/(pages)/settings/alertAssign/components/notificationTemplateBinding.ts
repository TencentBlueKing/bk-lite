import { ChannelItem } from '@/app/alarm/types/settings';

export interface NotificationTemplateOption {
  label: string;
  value: number;
}

export type NotificationTemplateBindings = Record<
  string,
  Partial<Record<'default' | 'reminder' | 'escalation' | 'recovery', number | null | undefined>>
>;

const TEMPLATE_SCENES = ['default', 'reminder', 'escalation', 'recovery'] as const;

export const getNotificationTemplateBindings = (channels: ChannelItem[]): NotificationTemplateBindings =>
  Object.fromEntries(channels.flatMap((channel) => {
    const source = channel.notification_templates;
    if (!source) return [];
    const bindings = Object.fromEntries(
      TEMPLATE_SCENES.flatMap((scene) => scene in source ? [[scene, source[scene]]] : []),
    );
    return [[channel.id.toString(), bindings]];
  }));

export const buildChannelsWithTemplateBindings = (
  selectedChannelIds: string[],
  channels: ChannelItem[],
  bindingsByChannel: NotificationTemplateBindings = {},
): ChannelItem[] => selectedChannelIds.flatMap((id) => {
  const channel = channels.find((item) => item.id.toString() === id);
  if (!channel) return [];
  const channelSnapshot = { ...channel };
  delete channelSnapshot.notification_templates;
  const bindings = Object.fromEntries(
    TEMPLATE_SCENES.flatMap((scene) => {
      const value = bindingsByChannel[id]?.[scene];
      return value === undefined ? [] : [[scene, value]];
    }),
  );
  return [{
    ...channelSnapshot,
    ...(Object.keys(bindings).length > 0 ? { notification_templates: bindings } : {}),
  }];
});
