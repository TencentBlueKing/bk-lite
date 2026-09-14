import { describe, expect, it } from 'vitest';
import {
  formatAuthHeaderPlainText,
  formatChoices,
  formatChoicesDisplay,
  injectDescriptionKey,
  splitLinkPlaceholder,
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

describe('auth header key link copy', () => {
  it('splits the {link} placeholder for JSX interpolation', () => {
    expect(splitLinkPlaceholder('可在「{link}」中生成与管理令牌。')).toEqual([
      '可在「',
      '」中生成与管理令牌。',
    ]);
    expect(splitLinkPlaceholder('Manage tokens under {link}.')).toEqual([
      'Manage tokens under ',
      '.',
    ]);
    expect(splitLinkPlaceholder('no placeholder')).toEqual(['no placeholder', '']);
  });

  it('joins desc, hint and path for PDF plain text', () => {
    expect(
      formatAuthHeaderPlainText(
        'Authorization: Bearer <API_TOKEN>。',
        '可在「{link}」中生成与管理令牌。',
        '平台设置 → 密钥',
      ),
    ).toBe('Authorization: Bearer <API_TOKEN>。 可在「平台设置 → 密钥」中生成与管理令牌。');
  });
});
