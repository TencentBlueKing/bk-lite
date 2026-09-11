import { describe, expect, it } from 'vitest';
import {
  formatChoices,
  formatChoicesDisplay,
  injectDescriptionKey,
} from '@/app/system-manager/utils/openapiDocs';

describe('formatChoices', () => {
  it('joins arrays and treats empty as blank', () => {
    expect(formatChoices(['patch_target', 'host'])).toBe('patch_target, host');
    expect(formatChoices(null)).toBe('');
    expect(formatChoicesDisplay(null)).toBe('--');
    expect(formatChoicesDisplay(['a'])).toBe('a');
  });
});

describe('injectDescriptionKey', () => {
  it('maps known inject types and falls back for unknown values', () => {
    expect(injectDescriptionKey('team_list')).toBe(
      'system.settings.openapiDocs.injectTeamList',
    );
    expect(injectDescriptionKey('custom')).toBe(
      'system.settings.openapiDocs.injectUnknown',
    );
  });
});
