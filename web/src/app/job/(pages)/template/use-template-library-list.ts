import { useEffect, useState } from 'react';
import type { TablePaginationConfig } from 'antd';
import useBatchSelection from '@/app/job/components/use-batch-selection';
import useApiClient from '@/utils/request';

interface NameFilter {
  name?: string;
}

interface LibraryListOptions<T> {
  resource: 'script' | 'playbook';
  loadPage: (params: NameFilter & { page: number; page_size: number }) => Promise<{ items: T[]; count: number }>;
  loadIds: (filter: NameFilter) => Promise<{ ids: number[] }>;
}

export default function useTemplateLibraryList<T>({ resource, loadPage, loadIds }: LibraryListOptions<T>) {
  const { isLoading: waitingForApi } = useApiClient();
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKey, setSearchKey] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [revision, setRevision] = useState(0);
  const selection = useBatchSelection({
    resource, total, pageSize, loading,
    loadIds: () => loadIds(appliedSearch ? { name: appliedSearch } : {}),
  });

  useEffect(() => {
    if (waitingForApi) return;
    let active = true;
    setLoading(true);
    const fetchPage = async () => {
      try {
        const result = await loadPage({ page: current, page_size: pageSize, ...(appliedSearch && { name: appliedSearch }) });
        if (!active) return;
        setTotal(result.count);
        const lastPage = Math.max(1, Math.ceil(result.count / pageSize));
        if (current > lastPage) {
          setCurrent(lastPage);
          return;
        }
        setData(result.items);
      } catch {
        if (!active) return;
        setData([]);
        setTotal(0);
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchPage();
    return () => { active = false; };
  }, [loadPage, waitingForApi, current, pageSize, appliedSearch, revision]);

  const fetchData = () => setRevision(value => value + 1);
  const handleSearch = (value: string) => {
    const name = value.trim();
    setSearchKey(value);
    if (name !== appliedSearch) {
      selection.clearSelection();
      setData([]);
      setTotal(0);
      setAppliedSearch(name);
    } else if (current === 1) {
      fetchData();
    }
    setLoading(true);
    setCurrent(1);
  };
  const handleTableChange = (page: TablePaginationConfig) => {
    setCurrent(page.current ?? 1);
    setPageSize(page.pageSize ?? pageSize);
  };
  return {
    data, loading, searchKey, setSearchKey, appliedSearch, fetchData, handleSearch, handleTableChange,
    pagination: { current, total, pageSize }, selection,
  };
}
