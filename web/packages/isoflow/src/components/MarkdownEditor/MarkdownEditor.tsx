import React, { useEffect, useRef, useCallback } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';
import { Box } from '@mui/material';

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
          const content = quill.root.innerHTML;
          onChange(content);
        }
      });
    }

    quillRef.current = quill;
  }, [onChange, placeholder, readOnly]);

  useEffect(() => {
    initializeQuill();
  }, [initializeQuill]);

  useEffect(() => {
    if (quillRef.current && !isUpdatingRef.current) {
      isUpdatingRef.current = true;
      quillRef.current.root.innerHTML = value;
      isUpdatingRef.current = false;
    }
  }, [value]);

  return (
    <Box
      sx={{
        '.ql-toolbar.ql-snow': {
          border: 'none',
          pt: 0,
          px: 0,
          ...(readOnly ? { display: 'none' } : {})
        },
        '.ql-toolbar.ql-snow + .ql-container.ql-snow': {
          border: '1px solid',
          borderColor: 'grey.300',
          borderTop: 'auto',
          borderRadius: 1.5,
          height,
          color: 'text.secondary'
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
