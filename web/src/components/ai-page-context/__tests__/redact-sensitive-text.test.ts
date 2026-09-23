import { describe, expect, it } from 'vitest';

import { redactSensitiveText } from '../redact-sensitive-text';

describe('redactSensitiveText', () => {
  it('replaces Bearer tokens without dropping the surrounding log line', () => {
    expect(redactSensitiveText('auth failed Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload'))
      .toBe('auth failed Authorization: Bearer [已省略]');
  });

  it('replaces password, api_key and token assignments', () => {
    expect(redactSensitiveText('login password=hunter2 api_key: abcd token=xyz'))
      .toBe('login key=[已省略] key=[已省略] key=[已省略]');
  });

  it('does not redact ordinary log text', () => {
    const line = 'timeout connecting to host-a:8080 error_count=3';
    expect(redactSensitiveText(line)).toBe(line);
  });
});
