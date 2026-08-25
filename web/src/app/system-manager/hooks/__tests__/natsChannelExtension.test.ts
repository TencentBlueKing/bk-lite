import { describe, expect, it } from 'vitest';

interface NatsChannelHelpers {
  normalizeNatsChannelConfig: (config: Record<string, unknown>) => Record<string, unknown>;
  usesEnterpriseNatsTestEndpoint: (config: Record<string, unknown>) => boolean;
}

const loadEnterpriseNatsHelpers = (): NatsChannelHelpers | null => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/app/system-manager/(enterprise)/hooks/useNatsNotificationExtension') as Partial<NatsChannelHelpers>;
    if (
      typeof mod.normalizeNatsChannelConfig !== 'function' ||
      typeof mod.usesEnterpriseNatsTestEndpoint !== 'function'
    ) {
      return null;
    }
    return {
      normalizeNatsChannelConfig: mod.normalizeNatsChannelConfig,
      usesEnterpriseNatsTestEndpoint: mod.usesEnterpriseNatsTestEndpoint,
    };
  } catch {
    return null;
  }
};

const natsHelpers = loadEnterpriseNatsHelpers();
const describeNats = natsHelpers ? describe : describe.skip;

describeNats('normalizeNatsChannelConfig', () => {
  if (!natsHelpers) {
    return;
  }

  const { normalizeNatsChannelConfig, usesEnterpriseNatsTestEndpoint } = natsHelpers;

  it('keeps only Event Publish settings when switching from Request/Reply', () => {
    expect(normalizeNatsChannelConfig({
      nats_mode: 'event_publish',
      subject_key: 'customer-alerts',
      namespace: 'bklite',
      method_name: 'receive_alert_events',
      timeout: 60,
    })).toEqual({
      nats_mode: 'event_publish',
      subject_key: 'customer-alerts',
      supports_notify_person: true,
    });
  });

  it('keeps only Request/Reply settings when switching from Event Publish', () => {
    expect(normalizeNatsChannelConfig({
      nats_mode: 'request_reply',
      subject_key: 'customer-alerts',
      namespace: 'bklite',
      method_name: 'receive_alert_events',
      timeout: 60,
    })).toEqual({
      nats_mode: 'request_reply',
      namespace: 'bklite',
      method_name: 'receive_alert_events',
      timeout: 60,
      supports_notify_person: true,
    });
  });

  it('preserves the notify-person switch across mode changes', () => {
    expect(normalizeNatsChannelConfig({
      nats_mode: 'event_publish',
      subject_key: 'alerts',
      supports_notify_person: false,
      namespace: 'bklite',
    }).supports_notify_person).toBe(false);
    expect(normalizeNatsChannelConfig({
      nats_mode: 'request_reply',
      supports_notify_person: true,
      subject_key: 'alerts',
    }).supports_notify_person).toBe(true);
  });

  it('rejects Event Publish settings without a notification topic identifier', () => {
    expect(() => normalizeNatsChannelConfig({
      nats_mode: 'event_publish',
      subject_key: '',
    })).toThrow('subject_key is required');
  });

  it('uses the Enterprise test endpoint only for Event Publish', () => {
    expect(usesEnterpriseNatsTestEndpoint({ nats_mode: 'event_publish' })).toBe(true);
    expect(usesEnterpriseNatsTestEndpoint({ nats_mode: 'request_reply' })).toBe(false);
    expect(usesEnterpriseNatsTestEndpoint({})).toBe(false);
  });
});
