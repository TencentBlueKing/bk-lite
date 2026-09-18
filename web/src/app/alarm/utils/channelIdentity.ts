export const channelOptionValue = (
  channel: { id: number; channel_type: string },
) => `${channel.channel_type}:${channel.id}`;
