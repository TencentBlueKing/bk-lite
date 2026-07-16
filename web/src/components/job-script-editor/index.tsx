'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactAce from 'react-ace';
import { Button, Tooltip, message } from 'antd';
import {
  CopyOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';
import 'ace-builds/src-noconflict/mode-sh';
import 'ace-builds/src-noconflict/mode-batchfile';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-powershell';
import 'ace-builds/src-noconflict/theme-monokai';

export type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';

interface LangConfig {
  label: string;
  mode: string;
}

const LANG_CONFIG: Record<ScriptLang, LangConfig> = {
  shell: { label: 'Shell', mode: 'sh' },
  bat: { label: 'Bat', mode: 'batchfile' },
  python: { label: 'Python', mode: 'python' },
  powershell: { label: 'Powershell', mode: 'powershell' },
};

const LANG_ORDER: ScriptLang[] = ['shell', 'bat', 'python', 'powershell'];

export interface JobScriptEditorProps {
  value?: Record<ScriptLang, string>;
  onChange?: (value: Record<ScriptLang, string>) => void;
  activeLang?: ScriptLang;
  onLangChange?: (lang: ScriptLang) => void;
  onBlur?: () => void;
  readOnly?: boolean;
}

const JobScriptEditor: React.FC<JobScriptEditorProps> = ({
  value,
  onChange,
  activeLang: controlledLang,
  onLangChange,
  onBlur,
  readOnly = false,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const defaultScripts: Record<ScriptLang, string> = {
    shell: t('job.scriptTemplateShell'),
    bat: t('job.scriptTemplateBat'),
    python: t('job.scriptTemplatePython'),
    powershell: t('job.scriptTemplatePowershell'),
  };
  const [internalLang, setInternalLang] = useState<ScriptLang>('shell');
  const activeLang = controlledLang ?? internalLang;

  const [scripts, setScripts] = useState<Record<ScriptLang, string>>(() => {
    if (value) return value;
    const init: Record<string, string> = {};
    for (const lang of LANG_ORDER) {
      init[lang] = defaultScripts[lang];
    }
    return init as Record<ScriptLang, string>;
  });

  useEffect(() => {
    if (value) {
      setScripts(value);
    }
  }, [value]);

  useEffect(() => {
    if (value) return;
    setScripts((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const lang of LANG_ORDER) {
        if (!next[lang]) {
          next[lang] = defaultScripts[lang];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [defaultScripts, value]);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    message.destroy();
    if (isFullscreen && containerRef.current) {
      message.config({ getContainer: () => containerRef.current! });
    } else {
      message.config({ getContainer: () => document.body });
    }
  }, [isFullscreen]);

  useEffect(() => {
    return () => {
      message.config({ getContainer: () => document.body });
    };
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  const handleCopy = useCallback(() => {
    copy(scripts[activeLang]);
  }, [activeLang, copy, scripts]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  const handleTabClick = (lang: ScriptLang) => {
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

  return (
    <div
      ref={containerRef}
      className={`overflow-hidden rounded-md border border-(--color-border-1) ${isFullscreen ? 'flex flex-col' : ''}`}
    >
      <div
        className="flex items-center justify-between px-2"
        style={{
          height: 40,
          background: 'linear-gradient(180deg, #2d2d30 0%, #252526 100%)',
          borderBottom: '1px solid #1e1e1e',
        }}
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
        <div className="flex gap-1">
          <Tooltip
            title={t('common.copy')}
            placement="bottom"
            getPopupContainer={
              isFullscreen ? () => containerRef.current! : undefined
            }
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
            getPopupContainer={
              isFullscreen ? () => containerRef.current! : undefined
            }
          >
            <Button
              type="text"
              size="small"
              icon={
                isFullscreen ? (
                  <FullscreenExitOutlined style={{ color: '#969696' }} />
                ) : (
                  <FullscreenOutlined style={{ color: '#969696' }} />
                )
              }
              onClick={toggleFullscreen}
              className="hover:bg-[#3e3e42]!"
            />
          </Tooltip>
        </div>
      </div>
      <ReactAce
        mode={LANG_CONFIG[activeLang].mode}
        theme="monokai"
        value={scripts[activeLang]}
        onChange={handleEditorChange}
        onBlur={onBlur}
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
};

export default JobScriptEditor;
