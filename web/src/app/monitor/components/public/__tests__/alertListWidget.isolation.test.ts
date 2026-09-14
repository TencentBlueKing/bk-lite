import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const widgetSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../AlertListWidget.tsx'),
  'utf8',
);

describe('monitor alert list public widget', () => {
  it('stays on the monitor alert API and does not read alarm-center tickets', () => {
    expect(widgetSource).toContain("from '@/app/monitor/api'");
    expect(widgetSource).toContain(
      "from '@/app/monitor/(pages)/view/monitorAlarm'",
    );
    expect(widgetSource).toContain('readOnly');
    expect(widgetSource).not.toMatch(/from ['"]@\/app\/alarm/);
  });
});
