import { describe, expect, it } from 'vitest';

import {
  normalizeNatsChannelConfig,
  usesEnterpriseNatsTestEndpoint,
} from '../../../../../../enterprise/web/src/app/system-manager/hooks/useNatsNotificationExtension';


describe('normalizeNatsChannelConfig', () => {
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
    });
  });

  it('uses the Enterprise test endpoint only for Event Publish', () => {
    expect(usesEnterpriseNatsTestEndpoint({ nats_mode: 'event_publish' })).toBe(true);
    expect(usesEnterpriseNatsTestEndpoint({ nats_mode: 'request_reply' })).toBe(false);
    expect(usesEnterpriseNatsTestEndpoint({})).toBe(false);
  });
});
