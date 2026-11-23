import { describe, expect, it } from 'vitest';
import {
  collectIntegrationCapabilityFilterOptions,
  excludeNotificationChannelProviders,
} from '@/app/system-manager/utils/integrationCenter';

describe('notification channel packs stay out of the integration center', () => {
  const providers = [
    { key: 'wecom', capabilities: [{ key: 'login' }] },
    { key: 'tplpack', capabilities: [{ key: 'notification_channel' }] },
  ];

  it('drops notification channel packs from the new-instance type list', () => {
    expect(excludeNotificationChannelProviders(providers).map((item) => item.key)).toEqual(['wecom']);
  });

  it('omits notification_channel from the capability filter', () => {
    const options = collectIntegrationCapabilityFilterOptions(
      [
        { capabilities: [{ key: 'login' }, { key: 'notification_channel' }] },
      ],
      (key, fallback) => fallback || key,
    );
    expect(options.map((item) => item.value)).not.toContain('notification_channel');
    expect(options.map((item) => item.value)).toContain('login');
  });
});
