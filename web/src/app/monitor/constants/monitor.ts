import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';
import { ListItem } from '@/types';
import {
  LevelMap,
  UnitMap,
  StateMap,
  MonitorGroupMap,
  ObjectIconMap,
  ConfigTypeMap,
} from '@/app/monitor/types/monitor';

const useFrequencyList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('common.timeSelector.off'), value: 0 },
      { label: '1m', value: 60000 },
      { label: '5m', value: 300000 },
      { label: '10m', value: 600000 },
    ],
    [t]
  );
};

const useTimeRangeList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('common.timeSelector.15Minutes'), value: 15 },
      { label: t('common.timeSelector.30Minutes'), value: 30 },
      { label: t('common.timeSelector.1Hour'), value: 60 },
      { label: t('common.timeSelector.6Hours'), value: 360 },
      { label: t('common.timeSelector.12Hours'), value: 720 },
      { label: t('common.timeSelector.1Day'), value: 1440 },
      { label: t('common.timeSelector.7Days'), value: 10080 },
      { label: t('common.timeSelector.30Days'), value: 43200 },
      { label: t('common.timeSelector.custom'), value: 0 },
    ],
    [t]
  );
};

const useConditionList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: '=', name: '=' },
      { id: '!=', name: '!=' },
      { id: '=~', name: t('monitor.include') },
      { id: '!~', name: t('monitor.exclude') },
    ],
    [t]
  );
};

const useStateMap = (): StateMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      new: t('monitor.events.new'),
      recovered: t('monitor.events.recovery'),
      closed: t('monitor.events.closed'),
    }),
    [t]
  );
};

const useLevelList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('monitor.events.critical'), value: 'critical' },
      { label: t('monitor.events.error'), value: 'error' },
      { label: t('monitor.events.warning'), value: 'warning' },
    ],
    [t]
  );
};

const useMethodList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: 'SUM', value: 'sum', title: t('monitor.events.sumTitle') },
      {
        label: 'SUM_OVER_TIME',
        value: 'sum_over_time',
        title: t('monitor.events.sumOverTimeTitle'),
      },
      { label: 'MAX', value: 'max', title: t('monitor.events.maxTitle') },
      {
        label: 'MAX_OVER_TIME',
        value: 'max_over_time',
        title: t('monitor.events.maxOverTimeTitle'),
      },
      { label: 'MIN', value: 'min', title: t('monitor.events.minTitle') },
      {
        label: 'MIN_OVER_TIME',
        value: 'min_over_time',
        title: t('monitor.events.minOverTimeTitle'),
      },
      { label: 'AVG', value: 'avg', title: t('monitor.events.avgTitle') },
      {
        label: 'AVG_OVER_TIME',
        value: 'avg_over_time',
        title: t('monitor.events.avgOverTimeTitle'),
      },
      { label: 'COUNT', value: 'count', title: t('monitor.events.countTitle') },
      {
        label: 'LAST_OVER_TIME',
        value: 'last_over_time',
        title: t('monitor.events.lastOverTimeTitle'),
      },
    ],
    [t]
  );
};

const useScheduleList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('monitor.events.minutes'), value: 'min' },
      { label: t('monitor.events.hours'), value: 'hour' },
      { label: t('monitor.events.days'), value: 'day' },
    ],
    [t]
  );
};

const useInterfaceLabelMap = (): ObjectIconMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      interface: t('monitor.views.interface'),
      ifOperStatus: t('monitor.views.ifOperStatus'),
      ifHighSpeed: t('monitor.views.ifHighSpeed'),
      ifInErrors: t('monitor.views.ifInErrors'),
      ifOutErrors: t('monitor.views.ifOutErrors'),
      ifInUcastPkts: t('monitor.views.ifInUcastPkts'),
      ifOutUcastPkts: t('monitor.views.ifOutUcastPkts'),
      ifInOctets: t('monitor.views.ifInOctets'),
      ifOutOctets: t('monitor.views.ifOutOctets'),
    }),
    [t]
  );
};

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
};

const UNIT_LIST = [
  {
    label: 'Misc',
    children: [
      { label: 'none', value: 'none', unit: '' },
      {
        label: 'short',
        value: 'short',
        unit: '',
      },
      { label: 'percent (0-100)', value: 'percent', unit: '%' },
      { label: 'percent (0.0-1.0)', value: 'percentunit', unit: '%' },
    ],
  },
  {
    label: 'Data (IEC)',
    children: [
      { label: 'bits', value: 'bits', unit: 'b' },
      { label: 'bytes', value: 'bytes', unit: 'B' },
      { label: 'kibibytes', value: 'kbytes', unit: 'KiB' },
      { label: 'mebibytes', value: 'mbytes', unit: 'MiB' },
      { label: 'gibibytes', value: 'gbytes', unit: 'GiB' },
      { label: 'tebibytes', value: 'tbytes', unit: 'TiB' },
      { label: 'pebibytes', value: 'pbytes', unit: 'PiB' },
    ],
  },
  {
    label: 'Data (Metric)',
    children: [
      { label: 'bits', value: 'decbits', unit: 'b' },
      { label: 'bytes', value: 'decbytes', unit: 'B' },
      { label: 'kilobytes', value: 'deckbytes', unit: 'KB' },
      { label: 'megabytes', value: 'decmbytes', unit: 'MB' },
      { label: 'gigabytes', value: 'decgbytes', unit: 'GB' },
      { label: 'terabytes', value: 'dectbytes', unit: 'TB' },
      { label: 'petabytes', value: 'decpbytes', unit: 'PB' },
    ],
  },
  {
    label: 'Data Rate',
    children: [
      { label: 'packets/sec', value: 'pps', unit: 'p/s' },
      { label: 'bits/sec', value: 'bps', unit: 'b/s' },
      { label: 'bytes/sec', value: 'Bps', unit: 'B/s' },
      { label: 'kilobytes/sec', value: 'KBs', unit: 'KB/s' },
      { label: 'kilobits/sec', value: 'Kbits', unit: 'Kb/s' },
      { label: 'megabytes/sec', value: 'MBs', unit: 'MB/s' },
      { label: 'megabits/sec', value: 'Mbits', unit: 'Mb/s' },
      { label: 'gigabytes/sec', value: 'GBs', unit: 'GB/s' },
      { label: 'gigabits/sec', value: 'Gbits', unit: 'Gb/s' },
      { label: 'terabytes/sec', value: 'TBs', unit: 'TB/s' },
      { label: 'terabits/sec', value: 'Tbits', unit: 'Tb/s' },
      { label: 'petabytes/sec', value: 'PBs', unit: 'PB/s' },
      { label: 'petabits/sec', value: 'Pbits', unit: 'Pb/s' },
    ],
  },
  {
    label: 'Temperature',
    children: [
      { label: 'Celsius (°C)', value: 'celsius', unit: '°C' },
      { label: 'Fahrenheit (°F)', value: 'fahrenheit', unit: '°F' },
      { label: 'Kelvin (K)', value: 'kelvin', unit: 'K' },
    ],
  },
  {
    label: 'Time',
    children: [
      { label: 'Hertz (1/s)', value: 'hertz', unit: 'hz' },
      { label: 'nanoseconds (ns)', value: 'ns', unit: 'ns' },
      { label: 'microseconds (µs)', value: 'µs', unit: 'µs' },
      { label: 'milliseconds (ms)', value: 'ms', unit: 'ms' },
      { label: 'seconds (s)', value: 's', unit: 's' },
      { label: 'minutes (m)', value: 'm', unit: 'min' },
      { label: 'hours (h)', value: 'h', unit: 'hour' },
      { label: 'days (d)', value: 'd', unit: 'day' },
    ],
  },
  {
    label: 'Throughput',
    children: [
      { label: 'counts/sec (cps)', value: 'cps', unit: 'cps' },
      { label: 'ops/sec (ops)', value: 'ops', unit: 'ops' },
      { label: 'requests/sec (rps)', value: 'reqps', unit: 'reqps' },
      { label: 'reads/sec (rps)', value: 'rps', unit: 'rps' },
      { label: 'writes/sec (wps)', value: 'wps', unit: 'wps' },
      { label: 'I/O ops/sec (iops)', value: 'iops', unit: 'iops' },
      { label: 'counts/min (cpm)', value: 'cpm', unit: 'cpm' },
      { label: 'ops/min (opm)', value: 'opm', unit: 'opm' },
      { label: 'reads/min (rpm)', value: 'rpm', unit: 'rpm' },
      { label: 'writes/min (wpm)', value: 'wpm', unit: 'wpm' },
    ],
  },
  {
    label: 'Other',
    children: [
      { label: 'Watts (W)', value: 'watts', unit: 'W' },
      { label: 'Volts (V)', value: 'volts', unit: 'V' },
    ],
  },
];

const useMiddleWareFields = (): ObjectIconMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      ClickHouse: t('monitor.intergrations.servers'),
      Consul: t('monitor.intergrations.address'),
      Zookeeper: t('monitor.intergrations.servers'),
      default: t('monitor.intergrations.url'),
      defaultDes: t('monitor.intergrations.urlDes'),
      ClickHouseDes: t('monitor.intergrations.serversDes'),
      ConsulDes: t('monitor.intergrations.addressDes'),
      ZookeeperDes: t('monitor.intergrations.serversDes'),
    }),
    [t]
  );
};

const INDEX_CONFIG = [
  {
    name: 'Host',
    id: 1,
    dashboardDisplay: [
      {
        indexId: 'env.procs',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'load1',
        displayType: 'dashboard',
        sortIndex: 1,
        displayDimension: [],
        segments: [
          { value: 1, color: '#27C274' }, // 绿色区域
          { value: 2, color: '#FF9214' }, // 黄色区域
          { value: 4, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'load5',
        displayType: 'dashboard',
        sortIndex: 2,
        displayDimension: [],
        segments: [
          { value: 1.5, color: '#27C274' }, // 绿色区域
          { value: 3, color: '#FF9214' }, // 黄色区域
          { value: 5, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'disk.used',
        displayType: 'table',
        sortIndex: 3,
        displayDimension: ['Device', 'Value'],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'cpu_summary.usage',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: ['cpu'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'disk.is_use',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'mem.pct_used',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'io.util',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'net.speed_sent',
        displayType: 'lineChart',
        sortIndex: 8,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'net.speed_recv',
        displayType: 'lineChart',
        sortIndex: 9,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'progress', key: 'cpu_summary.usage' },
      { type: 'progress', key: 'mem.pct_used' },
      { type: 'value', key: 'load5' },
    ],
  },
  {
    name: 'Website',
    id: 2,
    dashboardDisplay: [
      {
        indexId: 'http_success.rate',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_duration',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_ssl',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_status_code',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'http_dns.lookup.time',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'http_success.rate' },
      { type: 'value', key: 'http_duration' },
      { type: 'enum', key: 'http_code' },
    ],
  },
  {
    name: 'Ping',
    id: 3,
    dashboardDisplay: [
      //   {
      //     indexId: 'ping_response_time',
      //     displayType: 'single',
      //     sortIndex: 0,
      //     displayDimension: [],
      //     style: {
      //       height: '200px',
      //       width: '15%',
      //     },
      //   },
      //   {
      //     indexId: 'ping_error_response_code',
      //     displayType: 'single',
      //     sortIndex: 1,
      //     displayDimension: [],
      //     style: {
      //       height: '200px',
      //       width: '15%',
      //     },
      //   },
    ],
    tableDiaplay: [
      { type: 'value', key: 'ping_response_time' },
      { type: 'enum', key: 'ping_error_response_code' },
    ],
  },
  {
    name: 'Pod',
    id: 4,
    dashboardDisplay: [
      {
        indexId: 'pod_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'pod_cpu_utilization',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_memory_utilization',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_io_writes',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_io_read',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'pod_status' },
      { type: 'progress', key: 'pod_cpu_utilization' },
      { type: 'progress', key: 'pod_memory_utilization' },
    ],
  },
  {
    name: 'Node',
    id: 5,
    dashboardDisplay: [
      {
        indexId: 'node_status_condition',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'node_cpu_load1',
        displayType: 'dashboard',
        sortIndex: 1,
        displayDimension: [],
        segments: [
          { value: 1, color: '#27C274' }, // 绿色区域
          { value: 2, color: '#FF9214' }, // 黄色区域
          { value: 4, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'node_cpu_load5',
        displayType: 'dashboard',
        sortIndex: 2,
        displayDimension: [],
        segments: [
          { value: 1.5, color: '#27C274' }, // 绿色区域
          { value: 3, color: '#FF9214' }, // 黄色区域
          { value: 5, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'node_cpu_utilization',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_app_memory_utilization',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_io_current',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_network_receive',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_network_transmit',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'node_status_condition' },
      { type: 'progress', key: 'node_cpu_utilization' },
      { type: 'progress', key: 'node_memory_utilization' },
    ],
  },
  {
    name: 'Cluster',
    id: 6,
    dashboardDisplay: [
      {
        indexId: 'cluster_pod_count',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'cluster_node_count',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'k8s_cluster',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'cluster_pod_count' },
      { type: 'value', key: 'cluster_node_count' },
    ],
  },
  {
    name: 'Switch',
    id: 7,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Loadbalance',
    id: 8,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Router',
    id: 9,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Firewall',
    id: 10,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Detection Device',
    id: 11,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Bastion Host',
    id: 12,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Scanning Device',
    id: 13,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Audit System',
    id: 14,
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
  },
  {
    name: 'Docker',
    id: 15,
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'docker_n_containers' }],
  },
  {
    name: 'Docker Container',
    id: 16,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'docker_container_status' },
      { type: 'progress', key: 'docker_container_cpu_usage_percent' },
      { type: 'progress', key: 'docker_container_mem_usage_percent' },
    ],
  },
  {
    name: 'Zookeeper',
    id: 17,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'zookeeper_uptime' },
      { type: 'value', key: 'zookeeper_avg_latency' },
    ],
  },
  {
    name: 'Apache',
    id: 18,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'apache_uptime' },
      { type: 'value', key: 'apache_req_per_sec' },
      { type: 'progress', key: 'apache_cpu_load' },
    ],
  },
  {
    name: 'ClickHouse',
    id: 19,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'clickhouse_events_query' },
      { type: 'value', key: 'clickhouse_events_inserted_rows' },
      { type: 'value', key: 'clickhouse_asynchronous_metrics_load_average1' },
    ],
  },
  {
    name: 'RabbitMQ',
    id: 20,
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'rabbitmq_overview_messages_ready' }],
  },
  {
    name: 'ActiveMQ',
    id: 21,
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'activemq_topic_consumer_count' }],
  },
  {
    name: 'Nginx',
    id: 22,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'nginx_requests' },
      { type: 'value', key: 'nginx_active' },
    ],
  },
  {
    name: 'Tomcat',
    id: 23,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'tomcat_connector_request_count' },
      { type: 'value', key: 'tomcat_connector_current_threads_busy' },
      { type: 'value', key: 'tomcat_connector_error_count' },
    ],
  },
  {
    name: 'Consul',
    id: 24,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'consul_health_checks_status' },
      { type: 'value', key: 'consul_health_checks_passing' },
    ],
  },
  {
    name: 'ElasticSearch',
    id: 25,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'elasticsearch_fs_total_available_in_bytes' },
      { type: 'value', key: 'elasticsearch_http_current_open' },
      { type: 'value', key: 'elasticsearch_indices_docs_count' },
    ],
  },
  {
    name: 'MongoDB',
    id: 26,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mongodb_connections_current' },
      { type: 'value', key: 'mongodb_latency_commands' },
      { type: 'value', key: 'mongodb_resident_megabytes' },
    ],
  },
  {
    name: 'Mysql',
    id: 27,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mysql_bytes_received' },
      { type: 'value', key: 'mysql_bytes_sent' },
      { type: 'value', key: 'mysql_connections_total' },
    ],
  },
  {
    name: 'Postgres',
    id: 28,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'postgresql_active_time' },
      { type: 'value', key: 'postgresql_blks_hit' },
    ],
  },
  {
    name: 'Redis',
    id: 29,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'redis_used_memory' },
      { type: 'value', key: 'redis_instantaneous_ops_per_sec' },
    ],
  },
  {
    name: 'Storage',
    id: 30,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
      { type: 'enum', key: 'ipmi_power_watts' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
      { type: 'value', key: 'ipmi_voltage_volts' },
    ],
  },
  {
    name: 'Hardware Server',
    id: 31,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
      { type: 'enum', key: 'ipmi_power_watts' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
      { type: 'value', key: 'ipmi_voltage_volts' },
    ],
  },
  {
    name: 'vCenter',
    id: 32,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'vmware_esxi_count' },
      { type: 'value', key: 'vmware_datastore_count' },
      { type: 'value', key: 'vmware_vm_count' },
    ]
  },
  {
    name: 'ESXI',
    id: 33,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'esxi_cpu_usage_average_gauge' },
      { type: 'value', key: 'esxi_mem_usage_average_gauge' },
      { type: 'value', key: 'esxi_disk_read_average_gauge' },
    ]
  },
  {
    name: 'DataStorage',
    id: 34,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'data_storage_disk_used_average_gauge' },
      { type: 'enum', key: 'data_storage_store_accessible_gauge' },
    ]
  },
  {
    name: 'VM',
    id: 35,
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'vm_cpu_usage_average_gauge' },
      { type: 'value', key: 'vm_mem_usage_average_gauge' },
      { type: 'value', key: 'vm_disk_io_usage_gauge' },
    ]
  },
];

const SCHEDULE_UNIT_MAP: UnitMap = {
  minMin: 1,
  minMax: 59,
  hourMin: 1,
  hourMax: 23,
  dayMin: 1,
  dayMax: 1,
};

const PERIOD_LIST: ListItem[] = [
  { label: '1min', value: 60 },
  { label: '5min', value: 300 },
  { label: '15min', value: 900 },
  { label: '30min', value: 1800 },
  { label: '1hour', value: 3600 },
  { label: '6hour', value: 21600 },
  { label: '12hour', value: 43200 },
  { label: '24hour', value: 86400 },
];

const COMPARISON_METHOD: ListItem[] = [
  { label: '>', value: '>' },
  { label: '<', value: '<' },
  { label: '=', value: '=' },
  { label: '≠', value: '!=' },
  { label: '≥', value: '>=' },
  { label: '≤', value: '<=' },
];

const MONITOR_GROUPS_MAP: MonitorGroupMap = {
  Host: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
  Website: {
    list: ['instance_id'],
    // list: ['instance_id', 'instance_name', 'host'],
    default: ['instance_id'],
  },
  Cluster: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
  Pod: {
    // list: ['instance_id', 'uid'],
    // default: ['instance_id', 'uid'],
    list: ['uid'],
    default: ['uid'],
  },
  Node: {
    // list: ['instance_id', 'node'],
    // default: ['instance_id', 'node'],
    list: ['node'],
    default: ['node'],
  },
  Switch: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
  Router: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
  Loadbalance: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
  Firewall: {
    list: ['instance_id'],
    default: ['instance_id'],
  },
};

const OBJECT_ICON_MAP: ObjectIconMap = {
  Host: 'Host',
  Website: 'Website',
  Cluster: 'K8S',
  Pod: 'K8S',
  Node: 'K8S',
  Router: 'Router',
  Switch: 'Switch',
  Firewall: 'Firewall',
  Loadbalance: 'Loadbalance',
  'Detection Device': 'DetectionDevice',
  'Bastion Host': 'BastionHost',
  'Scanning Device': 'ScanningDevice',
  'Audit System': 'AuditSystem',
};

const APPOINT_METRIC_IDS: string[] = [
  'cluster_pod_count',
  'cluster_node_count',
];

const TIMEOUT_UNITS: string[] = ['s'];

const COLLECT_TYPE_MAP: ObjectIconMap = {
  Host: 'host',
  Website: 'web',
  Ping: 'ping',
  'Router SNMP General': 'snmp',
  'Switch SNMP General': 'snmp',
  'Firewall SNMP General': 'snmp',
  'Loadbalance SNMP General': 'snmp',
  'Detection Device SNMP General': 'snmp',
  'Scanning Device SNMP General': 'snmp',
  'Bastion Host SNMP General': 'snmp',
  'Storage SNMP General': 'snmp',
  'Hardware Server SNMP General': 'snmp',
  'Hardware Server IPMI': 'ipmi',
  'Storage IPMI': 'ipmi',
  K8S: 'k8s',
  'SNMP Trap': 'trap',
  Docker: 'docker',
  RabbitMQ: 'middleware',
  Nginx: 'middleware',
  ActiveMQ: 'middleware',
  Apache: 'middleware',
  ClickHouse: 'middleware',
  Consul: 'middleware',
  Zookeeper: 'middleware',
  Tomcat: 'middleware',
  MongoDB: 'database',
  Mysql: 'database',
  Redis: 'database',
  Postgres: 'database',
  ElasticSearch: 'database',
  VMWare: 'vmware',
};

const OBJECT_INSTANCE_TYPE_MAP: ObjectIconMap = {
  Host: 'os',
  Website: 'web',
  Ping: 'ping',
  Switch: 'switch',
  Router: 'router',
  Firewall: 'firewall',
  Loadbalance: 'loadbalance',
  'Detection Device': 'detection_device',
  'Scanning Device': 'scanning_device',
  'Bastion Host': 'bastion_host',
  Storage: 'storage',
  'Hardware Server': 'hardware_server',
  Cluster: 'k8s',
  'SNMP Trap': 'snmp_trap',
  Docker: 'docker',
  RabbitMQ: 'rabbitmq',
  Nginx: 'nginx',
  ActiveMQ: 'activemq',
  Apache: 'apache',
  ClickHouse: 'clickhouse',
  Consul: 'consul',
  Zookeeper: 'zookeeper',
  Tomcat: 'tomcat',
  MongoDB: 'mongodb',
  Mysql: 'mysql',
  Redis: 'redis',
  Postgres: 'postgres',
  ElasticSearch: 'elasticsearch',
  vCenter: 'vmware',
};

const INSTANCE_TYPE_MAP: ObjectIconMap = {
  Host: 'os',
  Website: 'web',
  Ping: 'ping',
  'Router SNMP General': 'router',
  'Switch SNMP General': 'switch',
  'Firewall SNMP General': 'firewall',
  'Loadbalance SNMP General': 'loadbalance',
  'Detection Device SNMP General': 'detection_device',
  'Scanning Device SNMP General': 'scanning_device',
  'Bastion Host SNMP General': 'bastion_host',
  'Storage SNMP General': 'storage',
  'Hardware Server SNMP General': 'hardware_server',
  'Hardware Server IPMI': 'hardware_server',
  'Storage IPMI': 'storage',
  K8S: 'k8s',
  'SNMP Trap': 'snmp_trap',
  Docker: 'docker',
  RabbitMQ: 'rabbitmq',
  Nginx: 'nginx',
  ActiveMQ: 'activemq',
  Apache: 'apache',
  ClickHouse: 'clickhouse',
  Consul: 'consul',
  Zookeeper: 'zookeeper',
  Tomcat: 'tomcat',
  MongoDB: 'mongodb',
  Mysql: 'mysql',
  Redis: 'redis',
  Postgres: 'postgres',
  ElasticSearch: 'elasticsearch',
  VMWare: 'vmware',
};

const CONFIG_TYPE_MAP: ConfigTypeMap = {
  Host: ['cpu', 'disk', 'diskio', 'mem', 'net', 'processes', 'system'],
  Website: ['http_response'],
  Ping: ['ping'],
  'Router SNMP General': ['router'],
  'Switch SNMP General': ['switch'],
  'Firewall SNMP General': ['firewall'],
  'Loadbalance SNMP General': ['loadbalance'],
  'Detection Device SNMP General': ['detection_device'],
  'Scanning Device SNMP General': ['scanning_device'],
  'Bastion Host SNMP General': ['bastion_host'],
  'Storage SNMP General': ['storage'],
  'Hardware Server SNMP General': ['hardware_server'],
  'Hardware Server IPMI': ['hardware_server'],
  'Storage IPMI': ['storage'],
  K8S: ['k8s'],
  'SNMP Trap': ['snmp_trap'],
  Docker: ['docker'],
  RabbitMQ: ['rabbitmq'],
  Nginx: ['nginx'],
  ActiveMQ: ['activemq'],
  Apache: ['apache'],
  ClickHouse: ['clickhouse'],
  Consul: ['consul'],
  Zookeeper: ['zookeeper'],
  Tomcat: ['tomcat'],
  MongoDB: ['mongodb'],
  Mysql: ['mysql'],
  Redis: ['redis'],
  Postgres: ['postgres'],
  ElasticSearch: ['elasticsearch'],
  VMWare: ['http'],
};

const MANUAL_CONFIG_TEXT_MAP: ObjectIconMap = {
  Apache: `[[inputs.$config_type]]
    urls = ["$monitor_url"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  ClickHouse: `[[inputs.$config_type]]
    servers = ["$monitor_url"]
    username = "default"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Consul: `[[inputs.$config_type]]
    address = "$monitor_url"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  RabbitMQ: `[[inputs.$config_type]]
    url = "$monitor_url"
    username = "$username"
    password = "$password"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Tomcat: `[[inputs.$config_type]]
    url = "$monitor_url"
    username = "$username"
    password = "$password"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  ActiveMQ: `[[inputs.$config_type]]
    url = "$monitor_url"
    username = "$username"
    password = "$password"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Nginx: `[[inputs.$config_type]]
    urls = ["$monitor_url"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Zookeeper: `[[inputs.$config_type]]
    servers = ["$monitor_url"]
    timeout = "$timeouts"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  ElasticSearch: `[[inputs.$config_type]]
    servers = ["$server"]
    username = "$username"
    password = "$password"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  MongoDB: `[[inputs.$config_type]]
    servers = ["mongodb://$host:$port/?connect=direct"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Mysql: `[[inputs.$config_type]]
    servers = ["$username:$password@tcp($host:$port)/?tls=false"]
    metric_version = 2
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Redis: `[[inputs.$config_type]]
    servers = ["tcp://$host:$port"]
    username = ""
    password = "$password" 
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  Postgres: `[[inputs.$config_type]]
    address = "host=$host port=$port user=$username password=$password sslmode=disable"
    ignored_databases = ["template0", "template1"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
  default: `[[inputs.$config_type]]
    url = "$monitor_url"
    username = "$username"
    password = "$password"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
};

const NODE_STATUS_MAP: ObjectIconMap = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray',
};

const INIT_VIEW_MODAL_FORM = {
  instance_id_values: [],
  instance_name: '',
  instance_id: '',
  instance_id_keys: [],
  dimensions: [],
  title: '',
};

export {
  UNIT_LIST,
  INDEX_CONFIG,
  PERIOD_LIST,
  COMPARISON_METHOD,
  LEVEL_MAP,
  SCHEDULE_UNIT_MAP,
  MONITOR_GROUPS_MAP,
  OBJECT_ICON_MAP,
  APPOINT_METRIC_IDS,
  TIMEOUT_UNITS,
  COLLECT_TYPE_MAP,
  INSTANCE_TYPE_MAP,
  CONFIG_TYPE_MAP,
  OBJECT_INSTANCE_TYPE_MAP,
  NODE_STATUS_MAP,
  MANUAL_CONFIG_TEXT_MAP,
  INIT_VIEW_MODAL_FORM,
  useMiddleWareFields,
  useInterfaceLabelMap,
  useScheduleList,
  useMethodList,
  useLevelList,
  useConditionList,
  useTimeRangeList,
  useFrequencyList,
  useStateMap,
};
