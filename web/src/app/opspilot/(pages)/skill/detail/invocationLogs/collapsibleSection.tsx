import React, { useState } from 'react';
import { Button } from 'antd';
import { CopyOutlined, DownOutlined, RightOutlined } from '@ant-design/icons';

interface CollapsibleSectionProps {
  title: string;
  content: object;
  onCopy: (content: object) => void;
}

const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({ title, content, onCopy }) => {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="mb-4 rounded">
      <div className="flex p-1 justify-between items-center bg-[var(--color-fill-1)]">
        <div
          className="flex items-center cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          <Button
            type="text"
            size="small"
            icon={expanded ? <DownOutlined /> : <RightOutlined />}
          />
          <strong className="ml-2">{title}</strong>
        </div>

        <Button
          icon={<CopyOutlined />}
          type="link"
          size="small"
          onClick={() => onCopy(content)}
        >
        </Button>
      </div>

      {expanded && (
        <pre className="bg-[var(--color-fill-2)] text-[var(--color-text-3)] p-2 whitespace-pre-wrap overflow-auto">
          {JSON.stringify(content, null, 2)}
        </pre>
      )}
    </div>
  );
};

export default CollapsibleSection;
