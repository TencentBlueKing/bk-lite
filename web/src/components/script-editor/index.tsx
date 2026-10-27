'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactAce from 'react-ace';
import { Button, Table, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CopyOutlined,
  DoubleRightOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { insertTextAtRange, type TextPoint, type TextRange } from './insert-text';
import 'ace-builds/src-noconflict/mode-sh';
import 'ace-builds/src-noconflict/mode-batchfile';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-powershell';
import 'ace-builds/src-noconflict/theme-monokai';

export type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';

export interface ScriptVariable {
  key: string;
  description: string;
  token: Partial<Record<ScriptLang, string>>;
}

export interface ScriptVariablePanelOptions {
  visible?: boolean;
  followFullscreen?: boolean;
  defaultExpanded?: boolean;
  variables?: ScriptVariable[];
}

export interface ScriptEditorProps {
  value?: Partial<Record<ScriptLang, string>>;
  templates?: Partial<Record<ScriptLang, string>>;
  onChange?: (value: Record<ScriptLang, string>) => void;
  activeLang?: ScriptLang;
  onLangChange?: (lang: ScriptLang) => void;
  onBlur?: () => void;
  readOnly?: boolean;
  variablePanel?: ScriptVariablePanelOptions;
  onVariablePanelExpandedChange?: (expanded: boolean) => void;
}

interface LangConfig {
  label: string;
  mode: string;
}

interface VariableRow {
  key: string;
  token: string;
  description: string;
}

interface AceSelection {
  getRange: () => { start: TextPoint; end: TextPoint };
}

interface AceEditorHandle {
  editor: {
    selection: AceSelection;
    moveCursorTo: (row: number, column: number) => void;
    clearSelection: () => void;
    focus: () => void;
  };
}

const LANG_CONFIG: Record<ScriptLang, LangConfig> = {
  shell: { label: 'Shell', mode: 'sh' },
  bat: { label: 'Bat', mode: 'batchfile' },
  python: { label: 'Python', mode: 'python' },
  powershell: { label: 'Powershell', mode: 'powershell' },
};

const LANG_ORDER: ScriptLang[] = ['shell', 'bat', 'python', 'powershell'];

const emptyScripts = (source?: Partial<Record<ScriptLang, string>>): Record<ScriptLang, string> => {
  const scripts = {} as Record<ScriptLang, string>;
  for (const lang of LANG_ORDER) {
    scripts[lang] = source?.[lang] ?? '';
  }
  return scripts;
};

const toTextRange = (range: { start: TextPoint; end: TextPoint }): TextRange => ({
  start: { row: range.start.row, column: range.start.column },
  end: { row: range.end.row, column: range.end.column },
});

const ScriptEditor: React.FC<ScriptEditorProps> = ({
  value,
  templates,
  onChange,
  activeLang: controlledLang,
  onLangChange,
  onBlur,
  readOnly = false,
  variablePanel,
  onVariablePanelExpandedChange,
}) => {
  const { t } = useTranslation();
  const [internalLang, setInternalLang] = useState<ScriptLang>('shell');
  const activeLang = controlledLang ?? internalLang;
  const panelVisible = Boolean(variablePanel?.visible);
  const followFullscreen = Boolean(variablePanel?.followFullscreen);
  const [expanded, setExpanded] = useState(Boolean(variablePanel?.defaultExpanded));
  const [scripts, setScripts] = useState<Record<ScriptLang, string>>(() => (
    value ? emptyScripts(value) : emptyScripts(templates)
  ));
  const [isFullscreen, setIsFullscreen] = useState(false);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const aceRef = useRef<AceEditorHandle>(null);
  const selectionRef = useRef<TextRange | null>(null);
  const hasCursorRef = useRef(false);
  const pendingCursorRef = useRef<TextPoint | null>(null);

  useEffect(() => {
    if (!value) return;
    const next = emptyScripts(value);
    setScripts((prev) => (
      LANG_ORDER.every((lang) => prev[lang] === next[lang]) ? prev : next
    ));
  }, [value]);

  useEffect(() => {
    if (value) return;
    setScripts((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const lang of LANG_ORDER) {
        if (!next[lang] && templates?.[lang]) {
          next[lang] = templates[lang] ?? '';
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [templates, value]);

  useEffect(() => {
    onVariablePanelExpandedChange?.(panelVisible ? expanded : false);
  }, [expanded, onVariablePanelExpandedChange, panelVisible]);

  useEffect(() => {
    const cursor = pendingCursorRef.current;
    if (!cursor) return;
    pendingCursorRef.current = null;
    const editor = aceRef.current?.editor;
    editor?.moveCursorTo(cursor.row, cursor.column);
    editor?.clearSelection();
    editor?.focus();
  }, [scripts, activeLang]);

  useEffect(() => {
    message.destroy();
    if (isFullscreen && fullscreenRef.current) {
      message.config({ getContainer: () => fullscreenRef.current! });
    } else {
      message.config({ getContainer: () => document.body });
    }
  }, [isFullscreen]);

  useEffect(() => () => {
    message.config({ getContainer: () => document.body });
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const captureSelection = () => {
    const range = aceRef.current?.editor?.selection.getRange();
    if (!range) return;
    selectionRef.current = toTextRange(range);
    hasCursorRef.current = true;
  };

  const handleCopy = useCallback(async () => {
    try {
      const text = scripts[activeLang];
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      message.success(t('common.copySuccess'));
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      message.error(errorMsg);
    }
  }, [scripts, activeLang, t]);

  const toggleFullscreen = () => {
    if (!fullscreenRef.current) return;
    if (!isFullscreen) {
      fullscreenRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  const handleTabClick = (lang: ScriptLang) => {
    if (readOnly) return;
    if (onLangChange) {
      onLangChange(lang);
    } else {
      setInternalLang(lang);
    }
  };

  const handleEditorChange = (newValue: string) => {
    if (readOnly) return;
    const updated = { ...scripts, [activeLang]: newValue };
    setScripts(updated);
    onChange?.(updated);
  };

  const handleInsert = (token: string) => {
    if (readOnly || !token) return;
    const range = hasCursorRef.current ? selectionRef.current : null;
    const inserted = insertTextAtRange(scripts[activeLang] || '', range, token);
    pendingCursorRef.current = inserted.cursor;
    selectionRef.current = { start: inserted.cursor, end: inserted.cursor };
    hasCursorRef.current = true;
    handleEditorChange(inserted.value);
  };

  const rows = useMemo<VariableRow[]>(() => (
    (variablePanel?.variables ?? []).flatMap((item) => {
      const token = item.token[activeLang];
      if (!token) return [];
      return [{ key: item.key, token, description: item.description }];
    })
  ), [activeLang, variablePanel?.variables]);

  const columns = useMemo<ColumnsType<VariableRow>>(() => [
    {
      title: t('common.variableName'),
      dataIndex: 'token',
      key: 'token',
      width: '46%',
      ellipsis: true,
      render: (token: string) => (
        <span className="font-mono text-[var(--color-primary)]">{token}</span>
      ),
    },
    {
      title: t('common.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (description: string) => (
        <EllipsisWithTooltip text={description} className="block truncate" />
      ),
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 64,
      render: (_value, record) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          disabled={readOnly}
          onMouseDown={(event) => {
            event.preventDefault();
            if (hasCursorRef.current) captureSelection();
          }}
          onClick={() => handleInsert(record.token)}
        >
          {t('common.useVariable')}
        </Button>
      ),
    },
  ], [activeLang, onChange, readOnly, scripts, t]);

  const editor = (
    <div
      ref={followFullscreen ? undefined : fullscreenRef}
      className={`min-w-0 flex-1 overflow-hidden rounded-md border border-(--color-border-1) ${isFullscreen && !followFullscreen ? 'flex h-full flex-col' : ''}`}
    >
      <div
        className="flex h-10 items-center justify-between border-b border-[#1e1e1e] px-2"
        style={{ background: 'linear-gradient(180deg, #2d2d30 0%, #252526 100%)' }}
      >
        <div className="flex gap-0">
          {LANG_ORDER.map((lang) => (
            <button
              key={lang}
              type="button"
              onClick={() => handleTabClick(lang)}
              className={`cursor-pointer border-none px-3 py-1.5 text-sm transition-colors ${
                activeLang === lang
                  ? 'bg-[#1e1e1e] text-white'
                  : 'bg-transparent text-[#969696] hover:text-white'
              }`}
            >
              {LANG_CONFIG[lang].label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {panelVisible ? (
            <Tooltip
              title={t('common.variable')}
              placement="bottom"
              getPopupContainer={isFullscreen ? () => fullscreenRef.current! : undefined}
            >
              <Button
                type="text"
                size="small"
                aria-expanded={expanded}
                aria-label={t('common.optionalVariables')}
                className="hover:bg-[#3e3e42]!"
                icon={<span className="font-mono text-xs" style={{ color: '#969696' }}>{'{x}'}</span>}
                onClick={() => setExpanded((open) => !open)}
              />
            </Tooltip>
          ) : null}
          <Tooltip
            title={t('common.copy')}
            placement="bottom"
            getPopupContainer={isFullscreen ? () => fullscreenRef.current! : undefined}
          >
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined style={{ color: '#969696' }} />}
              onClick={handleCopy}
              className="hover:bg-[#3e3e42]!"
            />
          </Tooltip>
          <Tooltip
            title={isFullscreen ? t('common.exitFullscreen') : t('common.fullscreen')}
            placement="bottom"
            getPopupContainer={isFullscreen ? () => fullscreenRef.current! : undefined}
          >
            <Button
              type="text"
              size="small"
              icon={isFullscreen
                ? <FullscreenExitOutlined style={{ color: '#969696' }} />
                : <FullscreenOutlined style={{ color: '#969696' }} />}
              onClick={toggleFullscreen}
              className="hover:bg-[#3e3e42]!"
            />
          </Tooltip>
        </div>
      </div>
      <ReactAce
        ref={aceRef as React.Ref<ReactAce>}
        mode={LANG_CONFIG[activeLang].mode}
        theme="monokai"
        value={scripts[activeLang]}
        onChange={handleEditorChange}
        onFocus={captureSelection}
        onSelectionChange={() => {
          if (hasCursorRef.current) captureSelection();
        }}
        onBlur={() => {
          if (hasCursorRef.current) captureSelection();
          onBlur?.();
        }}
        readOnly={readOnly}
        width="100%"
        height={isFullscreen ? '100%' : '320px'}
        style={isFullscreen ? { flex: 1 } : {}}
        setOptions={{
          showPrintMargin: false,
          tabSize: 2,
          fontSize: 14,
        }}
      />
    </div>
  );

  const panel = panelVisible && expanded ? (
    <aside className="flex w-80 shrink-0 flex-col self-stretch overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-[var(--color-border-1)] px-3">
        <span className="text-sm font-medium text-[var(--color-text-1)]">{t('common.optionalVariables')}</span>
            <Button
              type="link"
              size="small"
              className="px-0"
              icon={<DoubleRightOutlined />}
              onClick={() => setExpanded(false)}
            >
              {t('common.collapse')}
            </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table
          size="small"
          pagination={false}
          rowKey="key"
          columns={columns}
          dataSource={rows}
          tableLayout="fixed"
        />
      </div>
    </aside>
  ) : null;

  return (
    <div
      ref={followFullscreen ? fullscreenRef : undefined}
      className={`flex min-w-0 items-stretch gap-2 ${isFullscreen && followFullscreen ? 'h-full' : ''}`}
    >
      {editor}
      {panel}
    </div>
  );
};

export default ScriptEditor;
