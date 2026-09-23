import { describe, expect, it } from 'vitest';
import {
  formatAuthHeaderPlainText,
  formatChoices,
  formatChoicesDisplay,
  generateCurlCommand,
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
        'Authorization: Bearer <TOKEN>。',
        '可在「{link}」中生成与管理令牌。',
        '平台管理 → API 令牌',
      ),
    ).toBe('Authorization: Bearer <TOKEN>。 可在「平台管理 → API 令牌」中生成与管理令牌。');
  });
});

const curlRow = {
  key: 'cmdb/instances',
  kind: 'internal' as const,
  service: 'cmdb',
  method: 'GET',
  path: '/openapi/v1/cmdb/instances',
  summary: 'list',
  docUrl: '',
  inject: 'team_list_with_user',
  permission: 'asset_info-View',
  requestSchema: {},
  searchText: 'cmdb instances',
};

describe('generateCurlCommand', () => {
  it('uses only a bearer token for personal keys', () => {
    const curl = generateCurlCommand(curlRow, 'personal', 'https://bklite.example.com');
    expect(curl).toContain('https://bklite.example.com/openapi/v1/cmdb/instances');
    expect(curl).toContain('Authorization: Bearer <TOKEN>');
    expect(curl).not.toContain('X-Bklite-Acting-User');
    expect(curl).not.toContain('X-Bklite-Acting-Team');
  });

  it('adds acting headers for system keys without a domain suffix', () => {
    const curl = generateCurlCommand(curlRow, 'system', 'https://bklite.example.com');
    expect(curl).toContain('https://bklite.example.com/openapi/v1/cmdb/instances');
    expect(curl).toContain('Authorization: Bearer <TOKEN>');
    expect(curl).toContain('X-Bklite-Acting-User: <username>');
    expect(curl).not.toContain('@<domain>');
    expect(curl).not.toContain('@domain');
    expect(curl).toContain('X-Bklite-Acting-Team: <team_id>');
  });
});
