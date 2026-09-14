'use client';
// NOCA:AI-Secret-Leak-Checker(工具误报:复制用户已揭示的接入示例不是硬编码密钥)

import { CopyOutlined } from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';

interface ExampleCopyBlockProps {
  text: string;
  enabled: boolean;
}

const ExampleCopyBlock = ({ text, enabled }: ExampleCopyBlockProps) => {
  const { copy } = useCopy();
  const iconClass = enabled
    ? 'absolute top-3 right-3 cursor-pointer hover:text-blue-500'
    : 'absolute top-3 right-3 cursor-not-allowed text-[var(--color-text-4)]';

  return (
    <div className="relative">
      <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
        <code>{text}</code>
      </pre>
      <CopyOutlined
        className={iconClass}
        onClick={() => {
          if (!enabled) return;
          copy(text); // NOCA:AI-Secret-Leak-Checker(工具误报:复制用户已揭示的接入示例)
        }}
      />
    </div>
  );
};

export default ExampleCopyBlock;
