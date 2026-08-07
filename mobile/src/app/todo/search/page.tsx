'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InfiniteScroll } from 'antd-mobile';
import { useRouter } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MobileSearchBar from '@/components/mobile-search-bar';
import { AlertCard } from '@/features/todo/alert-card';
import { listAlertLevels, listAlerts } from '@/features/todo/adapter';
import { buildSearchQuery, mergePage, type AlertLevel, type AlertSearchField, type TodoAlert } from '@/features/todo/model';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/todo/todo.module.css';

export default function TodoSearchPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [field, setField] = useState<AlertSearchField>('title');
  const [input, setInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<TodoAlert[]>([]);
  const [levels, setLevels] = useState<AlertLevel[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);
  const levelMap = useMemo(() => new Map(levels.map((level) => [String(level.levelId), level])), [levels]);

  const search = useCallback(async (
    nextPage: number,
    append = false,
    nextKeyword = keyword,
    nextField: AlertSearchField = field,
    preserveContent = false,
  ) => {
    const query = buildSearchQuery(nextField, nextKeyword, nextPage);
    if (!query) return false;
    const currentId = ++requestId.current;
    if (!append && !preserveContent) setStatus('loading');
    try {
      const [result, levelResult] = await Promise.all([
        listAlerts(query),
        levels.length ? Promise.resolve(levels) : listAlertLevels().catch(() => []),
      ]);
      if (currentId !== requestId.current) return false;
      setLevels(levelResult);
      setItems((current) => append ? mergePage(current, result.items, (item) => item.id) : result.items);
      setCount(result.count);
      setPage(nextPage);
      setStatus('ready');
      return true;
    } catch {
      if (currentId !== requestId.current) return false;
      setStatus(append || preserveContent ? 'ready' : 'error');
      return false;
    }
  }, [field, keyword, levels]);

  useEffect(() => () => {
    requestId.current += 1;
  }, []);

  const submit = (value: string) => {
    const normalized = value.trim();
    setInput(value);
    setKeyword(normalized);
    if (normalized) {
      void search(1, false, normalized);
      return;
    }
    requestId.current += 1;
    setItems([]);
    setCount(0);
    setPage(0);
    setStatus('idle');
  };

  const changeField = (nextField: AlertSearchField) => {
    if (nextField === field) return;
    setField(nextField);
    if (keyword) void search(1, false, keyword, nextField);
  };

  const clearSearch = () => {
    requestId.current += 1;
    setInput('');
    setKeyword('');
    setItems([]);
    setCount(0);
    setPage(0);
    setStatus('idle');
  };

  const fieldOptions: Array<{ key: AlertSearchField; label: string }> = [
    { key: 'title', label: t('todo.searchFields.title') },
    { key: 'content', label: t('todo.searchFields.content') },
    { key: 'alert_id', label: t('todo.searchFields.alertId') },
  ];

  return (
    <main className={styles.page}>
      <MobilePageHeader title={t('todo.searchAlerts')} backHref="/todo" />
      <div className={styles.searchTools}>
        <MobileSearchBar
          size="page"
          value={input}
          placeholder={t('todo.searchPlaceholder')}
          onChange={setInput}
          onSearch={submit}
          onClear={clearSearch}
        />
        <div className={styles.searchFields} role="group" aria-label={t('todo.searchField')}>
          {fieldOptions.map((option) => (
            <button key={option.key} type="button" className={`${styles.searchField} ${field === option.key ? styles.searchFieldActive : ''}`} aria-pressed={field === option.key} onClick={() => changeField(option.key)}>{option.label}</button>
          ))}
        </div>
      </div>
      <div className={styles.scroll} ref={scrollRef}>
        <div className={styles.refreshContent}>
          {status === 'loading' ? (
            <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
          ) : status === 'error' ? (
            <MobileResult kind="error" title={t('todo.searchFailed')} description={t('todo.retryHint')} actionLabel={t('common.retry')} onAction={() => void search(1)} />
          ) : status === 'idle' ? (
            <MobileResult kind="empty" title={t('todo.searchHint')} />
          ) : items.length === 0 ? (
            <MobileResult kind="empty" title={t('todo.noSearchResults')} description={t('todo.tryAnotherKeyword')} />
          ) : (
            <>
              <div className={styles.resultSummary}>{t('todo.resultCount', undefined, { count })}</div>
              <div className={styles.alertList}>
                {items.map((alert) => (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    level={levelMap.get(alert.levelId)}
                    statusLabel={t(`todo.status.${alert.status}`, alert.status || '--')}
                    operatorLabel={t('todo.fields.operator')}
                    onOpen={() => router.push(`/todo/alerts/detail?id=${alert.id}`)}
                  />
                ))}
                <InfiniteScroll loadMore={async () => { await search(page + 1, true); }} hasMore={items.length < count} />
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
