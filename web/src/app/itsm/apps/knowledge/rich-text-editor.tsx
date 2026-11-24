'use client';

import { AiEditor } from 'aieditor';
import { useEffect, useRef, type RefObject } from 'react';
import 'aieditor/dist/style.css';
import { useIntl } from 'react-intl';
import { useTranslation } from '@/utils/i18n';
import { useThemeMode } from '@/theme';
import { sanitizeArticleHtml } from './article-html';

interface RichTextEditorProps {
  editorRef: RefObject<AiEditor | null>;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}

export default function RichTextEditor({ editorRef, value, onChange, disabled }: RichTextEditorProps) {
  const { mode } = useThemeMode();
  const host = useRef<HTMLDivElement>(null);
  const content = useRef(value);
  content.current = value;
  const { locale } = useIntl();
  const { t } = useTranslation();
  const language = locale.startsWith('zh') ? 'zh' : 'en';
  const label = t('itsm.knowledge.body');

  useEffect(() => {
    if (!host.current) return;
    const editor = new AiEditor({
      element: host.current,
      content: sanitizeArticleHtml(content.current),
      contentRetention: false,
      draggable: false,
      lang: language,
      toolbarKeys: [
        'undo', 'redo', 'divider', 'heading', 'bold', 'italic', 'underline', 'strike',
        'divider', 'bullet-list', 'ordered-list', 'quote', 'code-block', 'link', 'table',
      ],
      ai: { commandsEnable: false, bubblePanelEnable: false },
      textSelectionBubbleMenu: { enable: false },
      htmlPasteConfig: { pasteProcessor: sanitizeArticleHtml },
      onCreated: current => {
        current.innerEditor.view.dom.setAttribute('role', 'textbox');
        current.innerEditor.view.dom.setAttribute('aria-label', label);
        current.innerEditor.view.dom.setAttribute('aria-multiline', 'true');
      },
      onChange: current => onChange(current.isEmpty() ? '' : current.getHtml()),
    });
    editorRef.current = editor;
    return () => {
      editorRef.current = null;
      editor.destroy();
    };
  }, [editorRef, language, label, onChange]);

  useEffect(() => {
    editorRef.current?.setEditable(!disabled);
  }, [disabled, editorRef]);

  useEffect(() => {
    editorRef.current?.changeTheme(mode === 'dark' ? 'dark' : 'light');
  }, [mode, editorRef]);

  return <div ref={host} className="h-80 min-w-0 rounded-md border border-[var(--color-border)]" />;
}
