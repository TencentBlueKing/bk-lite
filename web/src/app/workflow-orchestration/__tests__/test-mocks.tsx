import type { PropsWithChildren } from 'react';
import { vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultMessage?: string, values?: Record<string, unknown>) => {
      const template = key === 'common.builtin' ? '内置' : defaultMessage || key;
      return template.replace(/\{(\w+)\}/g, (match, name: string) => values?.[name] == null ? match : String(values[name]));
    },
  }),
}));

vi.mock('@/components/permission', () => ({
  default: ({ children, instPermissions }: PropsWithChildren<{ instPermissions?: string[] }>) => (
    <span data-instance-permissions={instPermissions?.join(',')}>{children}</span>
  ),
}));

vi.mock('@/components/code-editor', () => ({
  default: ({ value, mode, theme, height, onChange }: { value?: string; mode?: string; theme?: string; height?: string; onChange?: (value: string) => void }) => (
    <textarea aria-label={`code-editor-${mode || 'text'}`} data-height={height} data-theme={theme} value={value || ''} onChange={(event) => onChange?.(event.target.value)} />
  ),
}));

vi.mock('@/app/job/components/script-editor', () => ({
  default: ({
    activeLang,
    value,
    onLangChange,
    onChange,
  }: {
    activeLang: string;
    value: Record<string, string>;
    onLangChange?: (lang: string) => void;
    onChange?: (value: Record<string, string>) => void;
  }) => (
    <div>
      <div data-testid="script-editor-lang">{activeLang}</div>
      <textarea
        aria-label={`script-editor-${activeLang}`}
        value={value[activeLang] || ''}
        onChange={(event) => onChange?.({ ...value, [activeLang]: event.target.value })}
      />
      {(['shell', 'bat', 'python', 'powershell'] as const).map((lang) => (
        <button key={lang} type="button" onClick={() => onLangChange?.(lang)}>{lang}</button>
      ))}
    </div>
  ),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (isoString: string, format = 'YYYY-MM-DD HH:mm:ss') => {
      if (!isoString) return '';
      const match = isoString.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/);
      if (!match) return isoString;
      const [, date, time] = match;
      if (format === 'YYYY-MM-DD HH:mm:ss') return `${date} ${time}`;
      if (format === 'YYYY-MM-DD HH:mm') return `${date} ${time.slice(0, 5)}`;
      if (format === 'MM-DD HH:mm:ss') return `${date.slice(5)} ${time}`;
      if (format === 'MM-DD') return date.slice(5);
      return `${date} ${time}`;
    },
    timeZone: 'Asia/Shanghai',
  }),
}));
