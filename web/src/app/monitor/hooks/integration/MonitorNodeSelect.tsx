'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Select, Tooltip } from 'antd';
import {
  MONITOR_NODE_PAGE_SIZE,
  MONITOR_NODE_SEARCH_DELAY_MS,
  monitorNodeQueryCache,
  scheduleMonitorNodeSearch,
  shouldLoadNextMonitorNodePage,
} from './fetchMonitorNodePages';

export interface MonitorNodeOption {
  id?: string;
  value: string;
  label: string;
  disabled?: boolean;
  disabledReason?: string;
  [key: string]: unknown;
}

export interface MonitorNodePageResult {
  count?: number;
  nodes?: MonitorNodeOption[];
}

interface MonitorNodeSelectProps {
  value?: string | string[];
  onChange?: (value: string | string[]) => void;
  placeholder?: string;
  status?: '' | 'error' | 'warning';
  cacheScope?: string;
  loadNodes: (query: { page: number; pageSize: number; keyword: string }) => Promise<MonitorNodePageResult>;
  onNodesLoaded?: (nodes: MonitorNodeOption[]) => void;
  excludeValues?: Array<string | number>;
  componentProps?: Record<string, unknown>;
}

function nodeValue(node: MonitorNodeOption) {
  return String(node.value ?? node.id ?? '');
}

export default function MonitorNodeSelect({
  value,
  onChange,
  placeholder,
  status,
  cacheScope = 'default',
  loadNodes,
  onNodesLoaded,
  excludeValues = [],
  componentProps = {},
}: MonitorNodeSelectProps) {
  const [options, setOptions] = useState<MonitorNodeOption[]>([]);
  const [loading, setLoading] = useState(false);
  const pageRef = useRef(0);
  const totalRef = useRef(0);
  const keywordRef = useRef('');
  const loadingRef = useRef(false);
  const requestRef = useRef(0);
  const searchTimer = useRef<{ id?: number }>({});
  const knownRef = useRef(new Map<string, MonitorNodeOption>());
  const loadNodesRef = useRef(loadNodes);
  loadNodesRef.current = loadNodes;
  const cacheRef = useRef(monitorNodeQueryCache<MonitorNodeOption>(cacheScope));
  cacheRef.current = monitorNodeQueryCache<MonitorNodeOption>(cacheScope);

  const remember = (nodes: MonitorNodeOption[]) => {
    nodes.forEach((node) => {
      const id = nodeValue(node);
      if (id) knownRef.current.set(id, node);
    });
    onNodesLoaded?.(nodes);
  };

  const showEntry = (keyword: string, entry: { nodes: MonitorNodeOption[]; page: number; total: number }) => {
    keywordRef.current = keyword;
    pageRef.current = entry.page;
    totalRef.current = entry.total;
    remember(entry.nodes);
    setOptions(entry.nodes);
  };

  const loadPage = async (page: number, keyword: string, append: boolean) => {
    const cached = cacheRef.current.read(keyword);
    if (cached && page <= cached.page) {
      requestRef.current += 1;
      showEntry(keyword, cached);
      return;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    loadingRef.current = true;
    setLoading(true);
    try {
      const entry = await cacheRef.current.load({
        keyword,
        page,
        append,
        nodeId: nodeValue,
        fetchPage: () => loadNodesRef.current({
          page,
          pageSize: MONITOR_NODE_PAGE_SIZE,
          keyword,
        }),
      });
      if (requestId !== requestRef.current) return;
      showEntry(keyword, entry);
    } finally {
      if (requestId === requestRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const cached = cacheRef.current.read('');
    if (cached) {
      showEntry('', cached);
    } else {
      void loadPage(1, '', false);
    }
    return () => {
      if (searchTimer.current.id) window.clearTimeout(searchTimer.current.id);
    };
  }, [cacheScope]);

  const excluded = new Set(excludeValues.map((item) => String(item)));
  const selectedIds = (Array.isArray(value) ? value : value ? [value] : []).map((item) => String(item));
  const visible = options.filter((node) => !excluded.has(nodeValue(node)) || selectedIds.includes(nodeValue(node)));
  selectedIds.forEach((id) => {
    if (!visible.some((node) => nodeValue(node) === id) && knownRef.current.has(id)) {
      visible.unshift(knownRef.current.get(id)!);
    }
  });

  return (
    <Select
      {...componentProps}
      virtual
      showSearch
      filterOption={false}
      value={value}
      placeholder={placeholder}
      className="w-full"
      status={status || undefined}
      loading={loading}
      options={visible.map((node) => ({
        value: nodeValue(node),
        label: node.label,
        disabled: node.disabled,
        title: node.disabledReason ? `${node.label} · ${node.disabledReason}` : node.label,
      }))}
      optionRender={(option) => (
        <Tooltip title={option.data.title}>
          <span className="block min-w-0 truncate">{option.label}</span>
        </Tooltip>
      )}
      onChange={(next) => {
        onChange?.(next);
        if (searchTimer.current.id) window.clearTimeout(searchTimer.current.id);
        const cached = cacheRef.current.read('');
        if (cached) showEntry('', cached);
      }}
      onSearch={(text) => {
        scheduleMonitorNodeSearch(searchTimer.current, MONITOR_NODE_SEARCH_DELAY_MS, () => {
          const next = text.trim();
          if (next === keywordRef.current) return;
          const cached = cacheRef.current.read(next);
          if (cached) {
            requestRef.current += 1;
            showEntry(next, cached);
            return;
          }
          void loadPage(1, next, false);
        });
      }}
      onPopupScroll={(event) => {
        const target = event.target as HTMLElement;
        if (loadingRef.current || options.length >= totalRef.current) return;
        if (!shouldLoadNextMonitorNodePage(target.scrollTop, target.clientHeight, target.scrollHeight)) return;
        void loadPage(pageRef.current + 1, keywordRef.current, true);
      }}
    />
  );
}
