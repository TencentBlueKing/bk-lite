import React, { useState } from 'react';
import { DownOutlined, BookOutlined } from '@ant-design/icons';
import { SkillViewItem } from '@/app/opspilot/types/global';

interface SkillViewProps {
  items?: SkillViewItem[];
}

const SkillView: React.FC<SkillViewProps> = ({ items }) => {
  const [expanded, setExpanded] = useState(false);
  const visibleItems = (items || []).filter(item => item?.name);

  if (visibleItems.length === 0) return null;

  return (
    <div className="my-2 rounded-lg border border-[#d7e3ff] bg-[#f7faff] text-sm text-[var(--color-text-1)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
        onClick={() => setExpanded(prev => !prev)}
      >
        <span className="flex min-w-0 items-center gap-2">
          <BookOutlined className="text-[var(--color-primary)]" />
          <span className="font-medium">技能包命中</span>
          <span className="shrink-0 text-xs text-[var(--color-text-4)]">
            {visibleItems.length} 个
          </span>
        </span>
        <DownOutlined className={`text-xs text-[var(--color-text-3)] transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <div className="border-t border-[#d7e3ff] px-5 py-3">
          <ul className="m-0 space-y-3 pl-4">
            {visibleItems.map((item) => (
              <li key={item.id || item.name} className="leading-6">
                <div><span className="font-medium">名称：</span>{item.name}</div>
                {item.package_id && (
                  <div><span className="font-medium">包 ID：</span>{item.package_id}</div>
                )}
                {item.description && (
                  <div><span className="font-medium">说明：</span>{item.description}</div>
                )}
                {Array.isArray(item.missing_tools) && item.missing_tools.length > 0 && (
                  <div><span className="font-medium">待绑定工具：</span>{item.missing_tools.join('、')}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default SkillView;
