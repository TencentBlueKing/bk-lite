import { AiEditor, AiEditorOptions } from 'aieditor';
import 'aieditor/dist/style.css';

import { HTMLAttributes, forwardRef, useEffect, useRef } from 'react';

type AIEditorProps = Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> & {
  placeholder?: string;
  defaultValue?: string;
  value?: string;
  onChange?: (val: string) => void;
  options?: Omit<AiEditorOptions, 'element'>;
};

const AIEditor = forwardRef<HTMLDivElement, AIEditorProps>(function AIEditor(
  { placeholder, defaultValue, value, onChange, options, ...props }: AIEditorProps,
  ref
) {
  const divRef = useRef<HTMLDivElement>(null);
  const aiEditorRef = useRef<AiEditor | null>(null);

  useEffect(() => {
    if (!divRef.current) return;

    if (!aiEditorRef.current) {
      const aiEditor = new AiEditor({
        element: divRef.current,
        placeholder: placeholder,
        content: defaultValue,
        onChange: (ed) => {
          if (typeof onChange === 'function') {
            onChange(ed.getMarkdown());
          }
        },
        ...options,
      });

      aiEditorRef.current = aiEditor;
    }

    return () => {
      if (aiEditorRef.current) {
        aiEditorRef.current.destroy();
        aiEditorRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (ref) {
      if (typeof ref === 'function') {
        ref(divRef.current);
      } else {
        ref.current = divRef.current;
      }
    }
  }, [ref]);

  useEffect(() => {
    if (aiEditorRef.current && value !== aiEditorRef.current.getMarkdown()) {
      aiEditorRef.current.setContent(value || '');
    }
  }, [value]);

  return <div ref={divRef} {...props} style={{ height: '100%' }} />;
});

export default AIEditor;