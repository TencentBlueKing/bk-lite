import React, { useEffect, useRef, useCallback } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';
import { Box } from '@mui/material';

const BLANK_EDITOR_HTML = new Set(['', '<p><br></p>', '<p></p>']);

function sameEditorHtml(current: string, next: string) {
  return current === next || (BLANK_EDITOR_HTML.has(current) && BLANK_EDITOR_HTML.has(next));
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  height?: number;
  styles?: React.CSSProperties;
}

export const MarkdownEditor = ({ 
  value, 
  onChange, 
  placeholder, 
  readOnly = false,
  height = 20,
  styles
}: Props) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const quillRef = useRef<Quill | null>(null);
  const isUpdatingRef = useRef(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const initializeQuill = useCallback(() => {
    if (!editorRef.current || quillRef.current) return;

    const quill = new Quill(editorRef.current, {
      theme: 'snow',
      placeholder: readOnly ? undefined : placeholder,
      readOnly: readOnly,
      modules: {
        toolbar: readOnly ? false : [
          ['bold', 'italic', 'underline'],
          [{ list: 'ordered' }, { list: 'bullet' }],
          ['link'],
          ['clean']
        ]
      }
    });

    if (!readOnly) {
      quill.on('text-change', () => {
        if (!isUpdatingRef.current) {
          onChangeRef.current(quill.root.innerHTML);
        }
      });
    }

    quillRef.current = quill;
  }, [placeholder, readOnly]);

  useEffect(() => {
    initializeQuill();
  }, [initializeQuill]);

  useEffect(() => {
    const quill = quillRef.current;
    if (!quill) return;
    const next = value ?? '';
    // Assigning innerHTML rebuilds the contenteditable and drops the caret
    // at index 0, so the next character is inserted in front of the previous one.
    if (sameEditorHtml(quill.root.innerHTML, next)) return;

    const selection = quill.getSelection();
    isUpdatingRef.current = true;
    try {
      if (BLANK_EDITOR_HTML.has(next)) {
        quill.setText('', 'silent');
      } else {
        quill.setContents(quill.clipboard.convert({ html: next }), 'silent');
      }
      if (selection) {
        const maxIndex = Math.max(0, quill.getLength() - 1);
        const index = Math.min(selection.index, maxIndex);
        const length = Math.min(selection.length, Math.max(0, maxIndex - index));
        quill.setSelection(index, length, 'silent');
      }
    } finally {
      isUpdatingRef.current = false;
    }
  }, [value]);

  return (
    <Box
      sx={{
        width: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
        '.ql-toolbar.ql-snow': {
          border: 'none',
          pt: 0,
          px: 0,
          whiteSpace: 'nowrap',
          '.ql-formats': {
            marginRight: '8px'
          },
          ...(readOnly ? { display: 'none' } : {})
        },
        '.ql-toolbar.ql-snow + .ql-container.ql-snow': {
          boxSizing: 'border-box',
          width: '100%',
          border: '1px solid #DFE7F0',
          backgroundColor: '#FFFFFF',
          borderRadius: '6px',
          height,
          color: 'var(--color-text-1)'
        },
        '&:focus-within .ql-toolbar.ql-snow + .ql-container.ql-snow': {
          borderColor: 'var(--color-primary)'
        },
        '.ql-container.ql-snow': {
          ...(readOnly ? { border: 'none' } : {}),
          ...styles
        },
        '.ql-editor': {
          ...(readOnly ? { p: 0 } : {})
        }
      }}
    >
      <div 
        ref={editorRef} 
        style={{ 
          minHeight: height
        }} 
      />
    </Box>
  );
};
