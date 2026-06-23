import React, { useEffect, useMemo, useState } from 'react';
import { Spin } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import CustomTable from '@/components/custom-table';
import useSearchApi from '@/app/log/api/search';
import { TableDataItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import {
  buildLogPreviewSearchParams,
  getDefaultShowFields,
  shouldFetchLogPreview
} from './policyFormUtils';

interface LogPreviewProps {
  query?: string;
  logGroups?: React.Key[];
  showFields?: string[];
}

const LogPreview: React.FC<LogPreviewProps> = ({
  query,
  logGroups,
  showFields
}) => {
  const { t } = useTranslation();
  const { getLogs } = useSearchApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<TableDataItem[]>([]);
  const normalizedQuery = query?.trim();
  const fields = useMemo(() => getDefaultShowFields(showFields), [showFields]);
  const previewReady = shouldFetchLogPreview({
    query: normalizedQuery,
    logGroups
  });
  const logGroupKey = JSON.stringify(logGroups || []);

  useEffect(() => {
    if (!previewReady) {
      setLogs([]);
      return;
    }

    const abortController = new AbortController();
    const fetchPreview = async () => {
      try {
        setLoading(true);
        const data = await getLogs(
          buildLogPreviewSearchParams({
            query: normalizedQuery,
            logGroups
          }),
          { signal: abortController.signal }
        );
        const listData = (data || []).map((item: TableDataItem) => ({
          ...item,
          id: uuidv4()
        }));
        setLogs(listData);
      } catch {
        if (!abortController.signal.aborted) {
          setLogs([]);
        }
      } finally {
        if (!abortController.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchPreview().catch(() => undefined);
    return () => abortController.abort();
  }, [normalizedQuery, logGroupKey, previewReady]);

  const columns = fields.map((field) => {
    if (field === 'timestamp') {
      return {
        title: 'timestamp',
        dataIndex: '_time',
        key: '_time',
        width: 160,
        render: (value: string) =>
          value ? convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss') : '--'
      };
    }
    if (field === 'message') {
      return {
        title: 'message',
        dataIndex: '_msg',
        key: '_msg',
        width: 260,
        ellipsis: true
      };
    }
    return {
      title: field,
      dataIndex: field,
      key: field,
      width: 160,
      ellipsis: true
    };
  });

  return (
    <div className="border border-[var(--color-border-2)] rounded-md bg-[var(--color-bg-1)] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border-2)]">
        <span className="font-medium">{t('log.event.logPreview')}</span>
        <span className="text-[var(--color-text-3)]">
          {t('log.event.latestTenLogs')}
        </span>
      </div>
      {!previewReady ? (
        <div className="m-4 border border-dashed border-[var(--color-primary)] rounded px-4 py-5 text-[var(--color-text-3)] bg-[var(--color-bg-2)]">
          {t('log.event.logPreviewGuide')}
        </div>
      ) : (
        <Spin spinning={loading} className="block">
          <CustomTable
            size="small"
            columns={columns}
            dataSource={logs}
            pagination={false}
            rowKey="id"
            scroll={{ x: 520, y: 320 }}
          />
          <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--color-border-1)] text-[var(--color-text-3)]">
            <span>
              {t('log.event.displayFields')}：{fields.join('、')}
            </span>
            <span>{t('log.event.sortByTimeDesc')}</span>
          </div>
        </Spin>
      )}
    </div>
  );
};

export default LogPreview;
