import React, { useMemo } from 'react';
import { Table, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import useChartColors from './useChartColors';
import { useTranslation } from '@/utils/i18n';

interface DockerErrorTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

interface ErrorRow {
  key: string;
  container_name: string;
  image: string;
  errcount: number;
  last_time: string;
  ratio: number;
}

const DockerErrorTable: React.FC<DockerErrorTableProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();
  const { t } = useTranslation();

  const tableData = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return [];

    const displayMaps = config?.displayMaps || {};
    const nameField = displayMaps.key || 'container_name';
    const valueField = displayMaps.value || 'errcount';
    const imageField = displayMaps.imageField || 'image';
    const timeField = displayMaps.timeField || 'last_time';

    const maxVal = Math.max(
      ...rawData.map((item: any) => parseFloat(item[valueField]) || 0),
      1
    );

    return rawData.map((item: any, idx: number) => {
      const val = parseFloat(item[valueField]) || 0;
      return {
        key: `${idx}`,
        container_name: item[nameField] || '--',
        image: item[imageField] || '--',
        errcount: val,
        last_time: item[timeField] || '--',
        ratio: val / maxVal
      };
    });
  }, [rawData, config]);

  const columns: ColumnsType<ErrorRow> = [
    {
      title: t('log.analysis.docker.containerName'),
      dataIndex: 'container_name',
      key: 'container_name',
      width: 180,
      ellipsis: true,
      render: (text: string) => (
        <span className="font-medium" style={{ color: colors.textPrimary }}>
          {text}
        </span>
      )
    },
    {
      title: t('log.analysis.docker.image'),
      dataIndex: 'image',
      key: 'image',
      width: 200,
      ellipsis: true,
      render: (text: string) => (
        <span style={{ color: colors.textSecondary }}>{text}</span>
      )
    },
    {
      title: t('log.analysis.docker.errorCount'),
      dataIndex: 'errcount',
      key: 'errcount',
      width: 160,
      sorter: (a: ErrorRow, b: ErrorRow) => a.errcount - b.errcount,
      defaultSortOrder: 'descend',
      render: (val: number, record: ErrorRow) => (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-3 rounded-sm overflow-hidden" style={{ background: colors.splitLine }}>
            <div
              className="h-full rounded-sm transition-all"
              style={{
                width: `${record.ratio * 100}%`,
                background: colors.danger
              }}
            />
          </div>
          <span className="text-xs font-medium w-10 text-right" style={{ color: colors.textPrimary }}>
            {val}
          </span>
        </div>
      )
    },
    {
      title: t('log.analysis.docker.lastErrorTime'),
      dataIndex: 'last_time',
      key: 'last_time',
      width: 170,
      render: (text: string) => {
        if (!text || text === '--') return <span style={{ color: colors.textTertiary }}>--</span>;
        const d = new Date(text);
        const formatted = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
        return <span style={{ color: colors.textSecondary }}>{formatted}</span>;
      }
    }
  ];

  if (!loading && tableData.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <Table
        columns={columns}
        dataSource={tableData}
        pagination={false}
        size="small"
        loading={loading}
        scroll={{ y: 'calc(100% - 40px)' }}
      />
    </div>
  );
};

export default DockerErrorTable;
