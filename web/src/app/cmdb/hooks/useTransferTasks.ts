import { useCallback, useEffect, useRef, useState } from 'react';
import { useTransferApi } from '@/app/cmdb/api/transfer';
import type { TransferTask } from '@/app/cmdb/types/transfer';

export function useTransferTasks(open: boolean, onImportFinished: (task: TransferTask) => void, enabled = true) {
  const api = useTransferApi();
  const [tasks, setTasks] = useState<TransferTask[]>([]);
  const [error, setError] = useState('');
  const [canSubmit, setCanSubmit] = useState(true);
  const [loading, setLoading] = useState(false);
  const previous = useRef<Map<string, string>>(new Map());
  const finished = useRef(onImportFinished);
  finished.current = onImportFinished;
  const fetchList = useRef(api.list);
  fetchList.current = api.list;
  const generation = useRef(0);
  const mounted = useRef(true);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const identity = api.identity;

  const refresh = useCallback(async () => {
    if (!enabledRef.current) return;
    const request = ++generation.current;
    setLoading(true);
    try {
      const data = await fetchList.current();
      if (!mounted.current || !enabledRef.current || request !== generation.current) return;
      for (const task of data.items) {
        const old = previous.current.get(task.task_id);
        if (task.type === 'import' && old && ['queued', 'running'].includes(old) &&
            ['succeeded', 'partial_success', 'failed', 'interrupted'].includes(task.status)) finished.current(task);
      }
      previous.current = new Map(data.items.map(task => [task.task_id, task.status]));
      setTasks(data.items);
      setCanSubmit(data.can_submit);
      setError('');
    } catch (failure) {
      if (mounted.current && request === generation.current) setError(failure instanceof Error ? failure.message : 'Request failed');
    } finally {
      if (mounted.current && request === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    previous.current.clear();
    setTasks([]);
    setError('');
    if (!api.isLoading) void refresh();
    return () => { mounted.current = false; generation.current += 1; };
  }, [identity, api.isLoading, refresh]);

  const previousEnabled = useRef(enabled);
  useEffect(() => {
    if (enabled && !previousEnabled.current && !api.isLoading) void refresh();
    previousEnabled.current = enabled;
  }, [enabled, api.isLoading, refresh]);

  const active = tasks.some(task => ['queued', 'running'].includes(task.status));
  const previousOpen = useRef(open);
  useEffect(() => {
    if (open && !previousOpen.current && !api.isLoading) void refresh();
    previousOpen.current = open;
  }, [open, api.isLoading, refresh]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      if (enabled && !cancelled && !document.hidden && (active || error)) timer = setTimeout(async () => {
        await refresh();
        schedule();
      }, open ? 3000 : 15000);
    };
    const visible = () => {
      if (document.hidden) { if (timer) clearTimeout(timer); }
      else { void refresh(); schedule(); }
    };
    schedule();
    document.addEventListener('visibilitychange', visible);
    return () => { cancelled = true; if (timer) clearTimeout(timer); document.removeEventListener('visibilitychange', visible); };
  }, [active, error, open, enabled, refresh]);

  const submitted = useCallback((task: TransferTask) => {
    previous.current.set(task.task_id, task.status);
    setTasks(current => [task, ...current.filter(item => item.task_id !== task.task_id)].slice(0, 5));
    setCanSubmit(false);
    void refresh();
  }, [refresh]);
  return { tasks, error, loading, canSubmit, refresh, submitted };
}
