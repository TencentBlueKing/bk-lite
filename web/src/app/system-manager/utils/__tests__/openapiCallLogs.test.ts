import { describe, expect, it } from 'vitest';

import {
  formatOpenApiCallRequest,
  formatOpenApiCallResult,
  formatOpenApiCallTokenKind,
  formatOpenApiCallTokenSystemId,
  openApiCallErrorCode,
  openApiCallResultPositive,
} from '../openapiCallLogs';

const labels = {
  success: '成功',
  authPassed: '鉴权通过',
  authDenied: '鉴权拒绝',
  failure: '失败',
};

describe('formatOpenApiCallRequest', () => {
  it('joins method and path', () => {
    expect(
      formatOpenApiCallRequest({
        method: 'POST',
        path: '/openapi/v1/itsm/tickets',
      })
    ).toBe('POST /openapi/v1/itsm/tickets');
  });

  it('renders empty method as a display placeholder', () => {
    expect(
      formatOpenApiCallRequest({
        method: '',
        path: '/openapi/v1/itsm/tickets',
      })
    ).toBe('-- /openapi/v1/itsm/tickets');
  });
});

describe('formatOpenApiCallResult', () => {
  it('translates call_result and keeps error code on 200', () => {
    const denied = { call_result: 'auth_denied' as const, http_status: 403, error_code: 'SCOPE_DENIED' };
    expect(formatOpenApiCallResult(denied, labels)).toBe('鉴权拒绝');
    expect(openApiCallErrorCode(denied)).toBe('SCOPE_DENIED');
    expect(openApiCallResultPositive(denied)).toBe(false);

    const ok = { call_result: 'success' as const, http_status: 200, error_code: 'TRACE' };
    expect(formatOpenApiCallResult(ok, labels)).toBe('成功');
    expect(openApiCallErrorCode(ok)).toBe('TRACE');
    expect(openApiCallResultPositive(ok)).toBe(true);
  });

  it('does not treat http_status < 400 as success without call_result', () => {
    const row = { http_status: 200, error_code: '', call_result: 'failure' as const };
    expect(formatOpenApiCallResult(row, labels)).toBe('失败');
    expect(openApiCallResultPositive(row)).toBe(false);
  });

  it('labels auth_passed separately from success', () => {
    const row = { call_result: 'auth_passed' as const, http_status: 200, error_code: '' };
    expect(formatOpenApiCallResult(row, labels)).toBe('鉴权通过');
    expect(openApiCallErrorCode(row)).toBe('');
    expect(openApiCallResultPositive(row)).toBe(true);
  });
});

describe('formatOpenApiCallToken', () => {
  const kindLabels = { apiToken: '个人密钥', systemToken: '系统密钥' };

  it('labels personal and system keys and leaves unrecognized blank', () => {
    expect(formatOpenApiCallTokenKind({ credential_type: 'api_token' }, kindLabels)).toBe('个人密钥');
    expect(formatOpenApiCallTokenKind({ credential_type: 'system_token' }, kindLabels)).toBe('系统密钥');
    expect(formatOpenApiCallTokenKind({ credential_type: '' }, kindLabels)).toBe('--');
  });

  it('shows the system id only for system keys and never the numeric id', () => {
    expect(formatOpenApiCallTokenSystemId({ credential_type: 'api_token', token_id: 12 })).toBe('');
    expect(
      formatOpenApiCallTokenSystemId({
        credential_type: 'system_token',
        token_id: 3,
        system_id: 'itsm',
      })
    ).toBe('itsm');
    expect(
      formatOpenApiCallTokenSystemId({ credential_type: 'api_token', token_id: 4, system_id: 'itsm' })
    ).toBe('');
    expect(formatOpenApiCallTokenSystemId({ credential_type: '' })).toBe('');
  });
});
