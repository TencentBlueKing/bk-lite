import { describe, expect, it } from 'vitest';

import {
  canShowIncidentAssetChangeTab,
  resolveIncidentSelectedAssetUuid,
} from '../incidentPublicAssetChange';

const UUID_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const UUID_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

describe('canShowIncidentAssetChangeTab', () => {
  it('hides the tab when there is no cmdb id, ops-analysis is missing, or the widget is undeclared', () => {
    expect(
      canShowIncidentAssetChangeTab({
        hasOpsAnalysis: true,
        declared: true,
        instUuids: [],
      }),
    ).toBe(false);
    expect(
      canShowIncidentAssetChangeTab({
        hasOpsAnalysis: false,
        declared: true,
        instUuids: [UUID_A],
      }),
    ).toBe(false);
    expect(
      canShowIncidentAssetChangeTab({
        hasOpsAnalysis: true,
        declared: false,
        instUuids: [UUID_A],
      }),
    ).toBe(false);
  });

  it('shows the tab only when ops-analysis is sold, the widget is declared, and at least one instUuid exists', () => {
    expect(
      canShowIncidentAssetChangeTab({
        hasOpsAnalysis: true,
        declared: true,
        instUuids: [UUID_A],
      }),
    ).toBe(true);
  });
});

describe('resolveIncidentSelectedAssetUuid', () => {
  it('returns a single uuid and never silently keeps a stale selection', () => {
    expect(resolveIncidentSelectedAssetUuid([], '')).toBe('');
    expect(resolveIncidentSelectedAssetUuid([UUID_A], '')).toBe(UUID_A);
    expect(resolveIncidentSelectedAssetUuid([UUID_A, UUID_B], UUID_B)).toBe(
      UUID_B,
    );
    expect(resolveIncidentSelectedAssetUuid([UUID_A, UUID_B], 'gone')).toBe(
      UUID_A,
    );
  });

  it('may default to the first uuid when multiple assets exist and nothing is selected', () => {
    expect(resolveIncidentSelectedAssetUuid([UUID_A, UUID_B], '')).toBe(UUID_A);
  });
});
