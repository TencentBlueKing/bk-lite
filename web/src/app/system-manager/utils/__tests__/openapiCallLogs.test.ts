import { describe, expect, it } from 'vitest';

import {
  formatOpenApiCallRequest,
  formatOpenApiCallResult,
  formatOpenApiCallTokenKind,
  formatOpenApiCallTokenSystemId,
  openApiCallErrorCode,
} from '../openapiCallLogs';

const labels = { success: '成功', failure: '失败' };

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
  it('shows failure without joining the error code', () => {
    const row = { http_status: 403, error_code: 'SCOPE_DENIED' };
    expect(formatOpenApiCallResult(row, labels)).toBe('失败');
    expect(openApiCallErrorCode(row)).toBe('SCOPE_DENIED');
  });

  it('shows success without a status number or error code', () => {
    const row = { http_status: 200, error_code: '' };
    expect(formatOpenApiCallResult(row, labels)).toBe('成功');
    expect(openApiCallErrorCode(row)).toBe('');
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
