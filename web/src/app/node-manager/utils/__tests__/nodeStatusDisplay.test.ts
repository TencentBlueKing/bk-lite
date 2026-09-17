import { describe, expect, it } from 'vitest';

import {
  collectorStatusI18nKey,
  collectorStatusTagColor,
  extractCollectorMessage,
  nodeOnlineI18nKey,
  nodeOnlineTagColor,
  parseComponentVersions,
  resolveSidecarStatusMessage,
  summarizeCollectorStatuses,
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

  it('colors sidecar online state like the node list, and stays uncolored when unknown', () => {
    expect(nodeOnlineTagColor(true)).toBe('success');
    expect(nodeOnlineTagColor(false)).toBe('warning');
    expect(nodeOnlineTagColor(undefined)).toBeNull();
  });

  it('colors collector statuses with the telegraf palette', () => {
    expect(collectorStatusTagColor(0)).toBe('success');
    expect(collectorStatusTagColor('2')).toBe('error');
    expect(collectorStatusTagColor(3)).toBe('warning');
    expect(collectorStatusTagColor(12)).toBe('warning');
    expect(collectorStatusTagColor(10)).toBe('processing');
    expect(collectorStatusTagColor(4)).toBe('default');
    expect(collectorStatusTagColor(99)).toBe('default');
    expect(collectorStatusTagColor(undefined)).toBe('default');
  });

  it('groups collectors by status into copy plus count, in first-seen order', () => {
    expect(
      summarizeCollectorStatuses([
        { status: 0 },
        { status: 2 },
        { status: 0 },
        { status: '0' },
      ]),
    ).toEqual([
      {
        status: '0',
        i18nKey: 'node-manager.cloudregion.node.normal',
        tagColor: 'success',
        count: 3,
      },
      {
        status: '2',
        i18nKey: 'node-manager.cloudregion.node.error',
        tagColor: 'error',
        count: 1,
      },
    ]);
  });

  it('keeps an empty collector list empty instead of inventing an unknown group', () => {
    expect(summarizeCollectorStatuses([])).toEqual([]);
    expect(summarizeCollectorStatuses(undefined)).toEqual([]);
    expect(summarizeCollectorStatuses(null)).toEqual([]);
  });

  it('folds collectors that report no status into a single unknown group', () => {
    expect(
      summarizeCollectorStatuses([{ status: undefined }, { status: '' }]),
    ).toEqual([
      {
        status: '',
        i18nKey: 'node-manager.cloudregion.node.unknown',
        tagColor: 'default',
        count: 2,
      },
    ]);
  });

  it('extracts collector string messages from strings or objects cleanly', () => {
    expect(extractCollectorMessage('Running')).toBe('Running');
    expect(extractCollectorMessage({ final_message: 'Connection timed out' })).toBe(
      'Connection timed out',
    );
    expect(extractCollectorMessage({ message: 'Failed to bind port' })).toBe(
      'Failed to bind port',
    );
    expect(extractCollectorMessage(null)).toBe('');
    expect(extractCollectorMessage(undefined)).toBe('');
  });

  it('parses controller and collector component versions', () => {
    const parsed = parseComponentVersions([
      {
        component_type: 'controller',
        version: '1.2.0',
        latest_version: '1.3.0',
        upgradeable: true,
      },
      {
        component_type: 'collector',
        component_id: 'telegraf',
        version: '1.28.0',
        upgradeable: false,
      },
    ]);

    expect(parsed.controller).toEqual({
      version: '1.2.0',
      latest_version: '1.3.0',
      upgradeable: true,
    });
    expect(parsed.collectors.get('telegraf')).toEqual({
      version: '1.28.0',
      latest_version: undefined,
      upgradeable: false,
    });
  });

  it('filters stale healthy sidecar messages when node is offline', () => {
    // 离线且带有上次心跳存留的 healthy/reporting 英文/中文词汇 -> 过滤掉返回 null，不给前端展示矛盾文案
    expect(
      resolveSidecarStatusMessage(
        false,
        'Heartbeat healthy · collectors reporting',
      ),
    ).toBeNull();
    expect(resolveSidecarStatusMessage(false, 'Running normally')).toBeNull();
    expect(resolveSidecarStatusMessage(false, '心跳正常')).toBeNull();

    // 离线但带有真实故障/超时原因 -> 保留原因供排障
    expect(resolveSidecarStatusMessage(false, 'Heartbeat timeout')).toBe(
      'Heartbeat timeout',
    );
    expect(resolveSidecarStatusMessage(false, 'Connection reset by peer')).toBe(
      'Connection reset by peer',
    );

    // 离线无说明 -> 返回 null
    expect(resolveSidecarStatusMessage(false, '')).toBeNull();
    expect(resolveSidecarStatusMessage(false, null)).toBeNull();

    // 在线 -> 正常透出最新的 healthy/reporting 摘要
    expect(
      resolveSidecarStatusMessage(
        true,
        'Heartbeat healthy · collectors reporting',
      ),
    ).toBe('Heartbeat healthy · collectors reporting');
    expect(resolveSidecarStatusMessage(true, '')).toBeNull();
  });
});
