import React, { useState } from 'react';
import { BookOutlined, DownOutlined, ToolOutlined } from '@ant-design/icons';
import { SkillViewItem } from '@/app/opspilot/types/global';

interface SkillViewProps {
  items?: SkillViewItem[];
}

const SkillView: React.FC<SkillViewProps> = ({ items }) => {
  const [expanded, setExpanded] = useState(false);
  const visibleItems = (items || []).filter(item => item?.name);
  const missingToolCount = visibleItems.reduce((count, item) => (
    count + (Array.isArray(item.missing_tools) ? item.missing_tools.length : 0)
  ), 0);

  if (visibleItems.length === 0) return null;

  return (
    <div className="my-2 overflow-hidden rounded-lg border border-[#dbe7ff] bg-white text-xs text-[var(--color-text-1)] shadow-[0_2px_8px_rgba(30,64,175,0.08)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 bg-gradient-to-r from-[#f4f8ff] to-white px-3 py-1.5 text-left transition-colors hover:from-[#eff5ff]"
        onClick={() => setExpanded(prev => !prev)}
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#e8f0ff] text-[var(--color-primary)]">
            <BookOutlined className="text-sm" />
          </span>
          <span className="min-w-0">
            <span className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-[#172033]">技能包命中</span>
              <span className="rounded-full bg-[#e8f0ff] px-1.5 py-0 text-[10px] font-medium text-[var(--color-primary)]">
                {visibleItems.length} 个
              </span>
              {missingToolCount > 0 && (
                <span className="rounded-full bg-[#fff7e8] px-1.5 py-0 text-[10px] font-medium text-[#b7791f]">
                  缺少 {missingToolCount} 个工具
                </span>
              )}
            </span>
          </span>
        </span>
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--color-text-3)] transition-colors hover:bg-[#e8f0ff]">
          <DownOutlined className={`text-[10px] transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {expanded && (
        <div className="border-t border-[#e8eefc] bg-white px-4 py-3">
          {visibleItems.map((item) => (
            <div key={item.id || item.name} className="border-t border-[#eef2f8] py-3 first:border-t-0 first:pt-0 last:pb-0">
              <div className="mb-2 flex min-w-0 items-center gap-2">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#f0f5ff] text-xs font-semibold text-[var(--color-primary)]">
                  {(item.name || 'S').slice(0, 1).toUpperCase()}
                </span>
                <span className="truncate font-semibold text-[#172033]">{item.name}</span>
                {item.package_id && (
                  <span className="shrink-0 rounded-md border border-[#dde7f7] bg-[#f8fbff] px-2 py-0.5 text-xs text-[var(--color-text-3)]">
                    {item.package_id}
                  </span>
                )}
              </div>
              {item.description && (
                <p className="m-0 max-w-[72ch] text-[13px] leading-6 text-[var(--color-text-2)]">
                  {item.description}
                </p>
              )}
              {Array.isArray(item.missing_tools) && item.missing_tools.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-[#b7791f]">
                    <ToolOutlined />
                    待绑定工具
                  </span>
                  {item.missing_tools.map(tool => (
                    <span key={tool} className="rounded-md border border-[#f6d58d] bg-[#fffaf0] px-2 py-0.5 text-xs text-[#8a5a12]">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SkillView;
