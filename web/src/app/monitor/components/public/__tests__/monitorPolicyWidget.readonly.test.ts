import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const widgetSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../MonitorPolicyWidget.tsx'),
  'utf8',
);

describe('monitor policy public widget', () => {
  it('embeds the policy table as read-only and never builds edit URLs', () => {
    expect(widgetSource).toContain("from '@/app/monitor/(pages)/view/monitorPolicy'");
    expect(widgetSource).toContain('readOnly');
    expect(widgetSource).not.toContain('buildMonitorStrategyDetailUrl');
    expect(widgetSource).not.toContain("'edit'");
  });

  it('lets the host container drive the table height instead of the monitor viewport offset', () => {
    expect(widgetSource).toContain('fillContainer');
    expect(widgetSource).not.toContain('100vh');
  });
});
