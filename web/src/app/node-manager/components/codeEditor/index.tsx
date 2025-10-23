import React from 'react';
import ReactAce from 'react-ace';
import { Button, Tooltip } from 'antd';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/theme-monokai';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';
interface CodeEditorProps {
  value?: string; // 编辑器的内容
  className?: string;
  showCopy?: boolean; // 是否显示复制按钮
  [key: string]: any; // 其余 ReactAce 的属性
}

const CodeEditor: React.FC<CodeEditorProps> = ({
  value = '',
  showCopy = false,
  className = '',
  ...restProps
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  return (
    <div className={className}>
      {showCopy && (
        <div className="bg-[#272822] flex justify-end pr-[4px]">
          <Tooltip title={t('common.copy')}>
            <Button
              size="small"
              type="link"
              icon={<CopyOutlined />}
              onClick={() => {
                copy(value);
              }}
            ></Button>
          </Tooltip>
        </div>
      )}
      <ReactAce
        style={{
          marginTop: 0,
        }}
        value={value}
        setOptions={{
          showPrintMargin: false, // 禁用打印边界
        }}
        {...restProps}
      />
    </div>
  );
};

export default CodeEditor;
