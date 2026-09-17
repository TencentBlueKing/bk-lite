import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../monitorPolicy.tsx'),
  'utf8',
);

describe('MonitorPolicy local vs embed', () => {
  it('only builds the edit URL when the table is not read-only', () => {
    expect(source).toContain('!readOnly');
    expect(source).toContain("buildMonitorStrategyDetailUrl('edit'");
    expect(source).toContain('readOnly = false');
    expect(source).not.toContain('shouldOpenMonitorPolicyEdit');
  });

  it('drops the viewport scroll offset when a host asks the table to fill its container', () => {
    expect(source).toContain('fillContainer ? { x: 890 }');
    expect(source).toContain("{ y: 'calc(100vh - 360px)', x: 890 }");
  });
});
