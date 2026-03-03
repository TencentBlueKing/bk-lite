'use client';
import dynamic from 'next/dynamic';
import { Spin } from 'antd';

// 动态导入 AceEditor 避免 SSR 问题
const AceEditor = dynamic(
  async () => {
    const ace = await import('react-ace');
    await import('ace-builds/src-noconflict/mode-json');
    await import('ace-builds/src-noconflict/theme-tomorrow');
    await import('ace-builds/src-noconflict/ext-language_tools');
    return ace;
  },
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center" style={{ height: '400px' }}>
        <Spin />
      </div>
    ),
  }
);

interface JsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  height?: string;
  readOnly?: boolean;
}

/**
 * JSON 编辑器组件
 * 使用 react-ace 实现，支持语法高亮、自动补全等功能
 */
const JsonEditor = ({
  value,
  onChange,
  height = '400px',
  readOnly = false,
}: JsonEditorProps) => {
  return (
    <AceEditor
      mode="json"
      theme="tomorrow"
      value={value}
      onChange={onChange}
      name="json-editor"
      width="100%"
      height={height}
      fontSize={13}
      showPrintMargin={false}
      showGutter={true}
      highlightActiveLine={true}
      readOnly={readOnly}
      setOptions={{
        enableBasicAutocompletion: true,
        enableLiveAutocompletion: true,
        enableSnippets: false,
        showLineNumbers: true,
        tabSize: 2,
        useWorker: false, // 禁用 worker 避免跨域问题
      }}
      editorProps={{ $blockScrolling: true }}
      style={{
        border: '1px solid #d9d9d9',
        borderRadius: '6px',
      }}
    />
  );
};

export default JsonEditor;
