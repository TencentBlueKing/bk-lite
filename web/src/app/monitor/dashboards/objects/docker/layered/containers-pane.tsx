'use client';

import { Table } from 'antd';
import { ProInfoHint, ProSection } from '../../host/layered/pro-chrome';
import { formatMetricValue } from '../../../shared/utils/format';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import DockerDimensionChart from './dimension-chart';
import { dockerText, type DockerCopyKey } from './copy';
import { DOCKER_BLANK } from './reading';
import { formatPercent, type DockerProView, type InventoryRow } from './view';

interface ContainersPaneProps {
  view: DockerProView;
}

const bytesReading = (value: number): string => {
  if (!Number.isFinite(value)) return DOCKER_BLANK;
  if (value === 0) return '0 Bytes';
  const formatted = formatMetricValue(value, 'bytes');
  if (formatted.value === '--') return DOCKER_BLANK;
  return formatted.unit ? `${formatted.value} ${formatted.unit}` : formatted.value;
};

export default function DockerContainersPane({ view }: ContainersPaneProps) {
  const { t } = useDashboardText();
  const text = (key: DockerCopyKey) => dockerText(t, key);
  const charts = [
    view.cpu.visible ? {
      key: 'cpu',
      title: text('cpuTitle'),
      hint: text('cpuHint'),
      unit: 'percent' as const,
      formatReading: formatPercent,
      series: view.cpu.series
    } : null,
    view.memPercent.visible ? {
      key: 'mem-percent',
      title: text('memPercentTitle'),
      hint: text('memPercentHint'),
      unit: 'percent' as const,
      formatReading: formatPercent,
      series: view.memPercent.series
    } : null,
    view.memBytes.visible ? {
      key: 'mem-bytes',
      title: text('memBytesTitle'),
      hint: text('memBytesHint'),
      unit: 'bytes' as const,
      formatReading: bytesReading,
      series: view.memBytes.series
    } : null
  ].filter((item) => item != null);

  return (
    <div data-docker-containers="" className="flex flex-col gap-4">
      {charts.length ? (
        <ProSection title={text('sectionResources')}>
          <div className="flex flex-col gap-4">
            {charts.map((chart) => (
              <DockerDimensionChart
                key={chart.key}
                chartKey={chart.key}
                title={chart.title}
                hint={chart.hint}
                unit={chart.unit}
                formatReading={chart.formatReading}
                series={chart.series}
                emptyText={text('empty')}
                clearLabel={text('clearSelection')}
              />
            ))}
          </div>
        </ProSection>
      ) : null}
      <ProSection
        title={text('sectionInventory')}
        hint={<ProInfoHint kind="docker-inventory" text={text('inventoryHint')} />}
      >
        <div data-docker-inventory="">
        <Table<InventoryRow>
          size="small"
          rowKey="name"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
          dataSource={view.inventory}
          locale={{ emptyText: text('empty') }}
          columns={[
            {
              title: text('columnName'),
              dataIndex: 'name',
              render: (name: string) => <span data-docker-container-name="">{name}</span>
            },
            {
              title: (
                <span className="inline-flex items-center gap-1">
                  {text('cpuTitle')}
                  <ProInfoHint kind="docker-cpu" text={text('cpuHint')} />
                </span>
              ),
              dataIndex: 'cpu',
              defaultSortOrder: 'descend',
              sorter: (left, right) => (left.cpuSort ?? Number.NEGATIVE_INFINITY) - (right.cpuSort ?? Number.NEGATIVE_INFINITY)
            },
            {
              title: (
                <span className="inline-flex items-center gap-1">
                  {text('memPercentTitle')}
                  <ProInfoHint kind="docker-mem-percent" text={text('memPercentHint')} />
                </span>
              ),
              dataIndex: 'memPercent',
              sorter: (left, right) => (left.memSort ?? Number.NEGATIVE_INFINITY) - (right.memSort ?? Number.NEGATIVE_INFINITY)
            },
            {
              title: (
                <span className="inline-flex items-center gap-1">
                  {text('memBytesTitle')}
                  <ProInfoHint kind="docker-mem-bytes" text={text('memBytesHint')} />
                </span>
              ),
              dataIndex: 'memBytes'
            },
            {
              title: (
                <span className="inline-flex items-center gap-1">
                  {text('restartTitle')}
                  <ProInfoHint kind="docker-restart" text={text('restartHint')} />
                </span>
              ),
              dataIndex: 'restarts'
            }
          ]}
        />
        </div>
      </ProSection>
    </div>
  );
}
