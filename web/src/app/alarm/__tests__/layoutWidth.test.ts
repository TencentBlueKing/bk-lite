import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const alarmDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const read = (relativePath: string) =>
  readFileSync(resolve(alarmDir, relativePath), 'utf8');

describe('alarm list width in app-top chrome', () => {
  it('does not size the content pane against 100vw', () => {
    expect(read('(pages)/alarms/index.module.scss')).not.toMatch(
      /width:\s*calc\(\s*100vw/,
    );
    expect(read('(pages)/incidents/index.module.scss')).not.toMatch(
      /width:\s*calc\(\s*100vw/,
    );
  });

  it('lets the content pane shrink beside the filter rail', () => {
    const alarms = read('(pages)/alarms/index.module.scss');
    const incidents = read('(pages)/incidents/index.module.scss');

    expect(alarms).toMatch(/\.alertContent[\s\S]*min-width:\s*0/);
    expect(incidents).toMatch(/\.content[\s\S]*min-width:\s*0/);
  });

  it('does not give the table a viewport-based min width', () => {
    const sources = [
      read('(pages)/alarms/components/alarmTable.tsx'),
      read('(pages)/incidents/page.tsx'),
      read('components/alarm-table/index.tsx'),
    ].join('\n');

    expect(sources).not.toMatch(/x:\s*'calc\(100vw/);
  });
});
