import { describe, expect, it } from 'vitest';
import { stripLeadingH1 } from '../sectionMarkdown';

describe('stripLeadingH1', () => {
  it('removes leading H1 so drawer title is not duplicated', () => {
    const md = `# Intro

top text

## Prereqs
content one
`;
    const result = stripLeadingH1(md);
    expect(result).not.toContain('# Intro');
    expect(result).toContain('top text');
    expect(result).toContain('## Prereqs');
    expect(result).toContain('content one');
  });

  it('returns empty string when content is only an H1', () => {
    expect(stripLeadingH1('# ElasticSearch 监控接入指南\n')).toBe('');
    expect(stripLeadingH1('# ElasticSearch 监控接入指南')).toBe('');
  });

  it('leaves content without leading H1 unchanged', () => {
    const md = `## Prereqs\n\n- port 9200`;
    expect(stripLeadingH1(md)).toBe(md);
  });

  it('does not strip H1 that appears after other content', () => {
    const md = `intro\n\n# Later title\n\nbody`;
    expect(stripLeadingH1(md)).toBe(md);
  });

  it('handles empty / nullish input', () => {
    expect(stripLeadingH1('')).toBe('');
    expect(stripLeadingH1(undefined as unknown as string)).toBe('');
  });
});
