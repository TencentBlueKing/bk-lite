import { describe, expect, it } from 'vitest';

import {
  collectorStatusI18nKey,
  nodeOnlineI18nKey,
} from '../nodeStatusDisplay';

describe('node status display mapping', () => {
  it('maps sidecar active to online/offline copy, not a raw status code', () => {
    expect(nodeOnlineI18nKey(true)).toBe('node-manager.cloudregion.node.online');
    expect(nodeOnlineI18nKey(false)).toBe('node-manager.cloudregion.node.offline');
    expect(nodeOnlineI18nKey(undefined)).toBeNull();
  });

  it('maps collector statuses with the same telegraf vocabulary as the node list', () => {
    expect(collectorStatusI18nKey(0)).toBe('node-manager.cloudregion.node.normal');
    expect(collectorStatusI18nKey('2')).toBe('node-manager.cloudregion.node.error');
    expect(collectorStatusI18nKey(3)).toBe('node-manager.cloudregion.node.stopped');
    expect(collectorStatusI18nKey(99)).toBe('node-manager.cloudregion.node.unknown');
    expect(collectorStatusI18nKey(undefined)).toBe(
      'node-manager.cloudregion.node.unknown',
    );
  });
});
