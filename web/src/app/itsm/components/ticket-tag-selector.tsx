'use client';

import { useEffect, useState } from 'react';
import { Select, Spin } from 'antd';
import { useItsmApi } from '../api/useItsmApi';

export function TicketTagSelector({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [options, setOptions] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!api.ready) return;
    let active = true;
    setLoading(true); setError(false);
    const timer = window.setTimeout(() => {
      void api.searchTicketTags(keyword).then(result => {
        if (active) setOptions((result as { items: { name: string }[] }).items.map(item => ({ value: item.name, label: item.name })));
      }).catch(() => { if (active) { setOptions([]); setError(true); } }).finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [api.ready, api.searchTicketTags, keyword, refresh]);
  return <Select aria-label="筛选标签" className="w-40" showSearch allowClear filterOption={false} placeholder="搜索并选择标签"
    value={value || undefined} options={options} loading={loading} onSearch={setKeyword} onChange={next => onChange(next || '')}
    onOpenChange={open => { if (open) setRefresh(current => current + 1); }}
    notFoundContent={loading ? <Spin size="small" /> : error ? '加载失败，请重新展开重试' : '暂无可选标签'} />;
}
