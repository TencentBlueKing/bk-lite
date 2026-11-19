import { readFileSync } from 'node:fs';
import path from 'node:path';

import { WINDOWS_EVENT_BASE_QUERY } from '../windowsEventLogQueries';

describe('windows event dashboard query', () => {
  it('matches ingested winlogbeat logs instead of the sample dataset', () => {
    expect(WINDOWS_EVENT_BASE_QUERY).toBe('collect_type:"winlogbeat"');
    expect(WINDOWS_EVENT_BASE_QUERY).not.toContain('bk-lite-analysis-sample');
    expect(WINDOWS_EVENT_BASE_QUERY).not.toContain('event.dataset');
    expect(WINDOWS_EVENT_BASE_QUERY).not.toContain('service.name');
  });

  it('keeps the dashboard widgets on that base query', () => {
    const source = readFileSync(
      path.join(process.cwd(), 'src/app/log/hooks/analysis/windowsEventDashboard.tsx'),
      'utf8'
    );

    expect(source).toContain('WINDOWS_EVENT_BASE_QUERY');
    expect(source).not.toContain('bk-lite-analysis-sample');
    expect(source).not.toContain('event.dataset');
  });
});
