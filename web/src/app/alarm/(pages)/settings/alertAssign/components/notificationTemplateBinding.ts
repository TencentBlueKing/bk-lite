import { ChannelItem } from '@/app/alarm/types/settings';
import { channelOptionValue } from '@/app/alarm/utils/channelIdentity';

export interface NotificationTemplateOption {
  label: string;
  value: number;
}

const TEMPLATE_SCENES = ['default', 'reminder', 'escalation', 'recovery'] as const;

export type NotificationTemplateScene = (typeof TEMPLATE_SCENES)[number];

export type NotificationTemplateBindings = Record<
  string,
  Partial<Record<NotificationTemplateScene, number | null | undefined>>
>;

export const activeNotificationTemplateScenes = ({
  notificationScenario,
  notificationFrequency,
  escalationEnabled,
}: {
  notificationScenario?: string[] | null;
  notificationFrequency?: Record<string, { interval_minutes?: number | null } | null | undefined> | null;
  escalationEnabled?: boolean;
}): NotificationTemplateScene[] => {
  const scenes: NotificationTemplateScene[] = ['default'];
  const reminderEnabled = Object.values(notificationFrequency || {}).some(
    (level) => Number(level?.interval_minutes || 0) > 0,
  );
  if (reminderEnabled) scenes.push('reminder');
  if (escalationEnabled) scenes.push('escalation');
  if ((notificationScenario || []).includes('recovery')) scenes.push('recovery');
  return scenes;
};

export const getNotificationTemplateBindings = (channels: ChannelItem[]): NotificationTemplateBindings =>
  Object.fromEntries(channels.flatMap((channel) => {
    const source = channel.notification_templates;
    if (!source) return [];
    const bindings = Object.fromEntries(
      TEMPLATE_SCENES.flatMap((scene) => scene in source ? [[scene, source[scene]]] : []),
    );
    return [[channelOptionValue(channel), bindings]];
  }));

export const buildChannelsWithTemplateBindings = (
  selectedChannelIds: string[],
  channels: ChannelItem[],
  bindingsByChannel: NotificationTemplateBindings = {},
): ChannelItem[] => selectedChannelIds.flatMap((id) => {
  const channel = channels.find((item) => channelOptionValue(item) === id);
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
