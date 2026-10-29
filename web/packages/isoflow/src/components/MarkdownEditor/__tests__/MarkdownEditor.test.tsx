import React, { useState } from 'react';
import { act, cleanup, render } from '@testing-library/react';
import Quill from 'quill';
import { afterEach, describe, expect, it } from 'vitest';
import { MarkdownEditor } from '../MarkdownEditor';

function editorRoot() {
  const root = document.querySelector('.ql-editor');
  if (!(root instanceof HTMLElement)) {
    throw new Error('Quill editor was not mounted');
  }
  return root;
}

function quill() {
  const container = editorRoot().parentElement;
  const found = container ? Quill.find(container) : null;
  if (found == null || typeof found !== 'object' || !('getText' in found)) {
    throw new Error('Quill instance was not attached');
  }
  return found as Quill;
}

function ControlledEditor({ initial = '' }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return <MarkdownEditor value={value} onChange={setValue} />;
}

describe('MarkdownEditor', () => {
  afterEach(() => {
    cleanup();
  });

  it('keeps the caret text node when a keystroke is echoed back as the value', () => {
    let textNode: ChildNode | null = null;
    function Harness() {
      const [value, setValue] = useState('');
      return (
        <MarkdownEditor
          value={value}
          onChange={(next) => {
            textNode = editorRoot().querySelector('p')?.firstChild ?? null;
            setValue(next);
          }}
        />
      );
    }

    render(<Harness />);
    act(() => {
      quill().insertText(0, '1', 'user');
    });

    expect(textNode).not.toBeNull();
    expect(editorRoot().querySelector('p')?.firstChild).toBe(textNode);
    expect(quill().getText()).toBe('1\n');
  });

  it('inserts each character after the previous one', () => {
    render(<ControlledEditor />);
    const editor = quill();

    act(() => {
      editor.focus();
      editor.setSelection(0, 0, 'silent');
    });

    for (const char of '12345') {
      act(() => {
        const index = editor.getSelection()?.index ?? 0;
        editor.insertText(index, char, 'user');
        editor.setSelection(index + 1, 0, 'silent');
      });
    }

    expect(editor.getText()).toBe('12345\n');
  });

  it('replaces the document when the value changes from outside', () => {
    const view = render(<MarkdownEditor value="<p>before</p>" onChange={() => {}} />);

    expect(quill().getText()).toBe('before\n');

    view.rerender(<MarkdownEditor value="<p>after</p>" onChange={() => {}} />);

    expect(quill().getText()).toBe('after\n');
  });
});
