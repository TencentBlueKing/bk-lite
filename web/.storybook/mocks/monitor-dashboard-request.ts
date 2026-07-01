'use client';

import type { AxiosRequestConfig } from 'axios';

interface QueryRangeParams {
  query?: string;
  source_unit?: string;
  start?: number;
  end?: number;
  step?: number;
}

const nowSeconds = () => Math.floor(Date.now() / 1000);

const buildValues = (base: number, unit = 'none') => {
  const end = nowSeconds();
  const step = 60;
  return Array.from({ length: 36 }, (_, index) => {
    const wave = Math.sin(index / 4) * base * 0.08;
    const drift = Math.cos(index / 7) * base * 0.04;
    const value = Math.max(unit === 'percent' ? 0 : 0.01, base + wave + drift);
    return [end - (35 - index) * step, value.toFixed(unit === 'none' ? 0 : 2)] as [number, string];
  });
};

const inferBaseValue = (query = '', unit = 'none') => {
  if (query.startsWith('count(') || query.includes(' count(')) {
    if (query.includes('kube_node_info')) return 3;
    if (query.includes('kube_pod_info') && query.includes('namespace')) return 6;
    if (query.includes('kube_pod_info')) return 24;
    if (query.includes('kube_deployment')) return 8;
    if (query.includes('kube_daemonset')) return 3;
    if (query.includes('kube_statefulset')) return 4;
    return 1;
  }
  if (query.includes('http_response_result_type') && query.includes('success')) return 98.6;
  if (query.includes('http_response_response_time') && query.includes('max')) return 0.82;
  if (query.includes('http_response_response_time')) return 0.34;
  if (query.includes('http_response_content_length')) return 186 * 1024;
  if (query.includes('http_response_http_response_code') && query.includes('>= 200') && query.includes('< 300')) return 3;
  if (query.includes('http_response_http_response_code') && query.includes('>= 300') && query.includes('< 400')) return 0;
  if (query.includes('http_response_http_response_code') && query.includes('>= 400') && query.includes('< 500')) return 0;
  if (query.includes('http_response_http_response_code') && query.includes('>= 500')) return 0;
  if (query.includes('100 -') && query.includes('http_response_result_type')) return 1.4;
  if (query.includes('ping_percent_packet_loss')) return query.includes('100 -') ? 99.2 : 0.8;
  if (query.includes('ping_average_response_ms')) return 18;
  if (query.includes('ping_minimum_response_ms')) return 9;
  if (query.includes('ping_maximum_response_ms')) return 42;
  if (query.includes('ping_ttl')) return 64;
  if (query.includes('net_response_result_code') && query.includes('== bool 0')) return 99.5;
  if (query.includes('net_response_result_code') && query.includes('!= bool 0')) return 0.5;
  if (query.includes('net_response_string_found')) return 100;
  if (query.includes('net_response_response_time')) return 0.06;
  if (query.includes('net_response_result_code')) return 0;
  if (query.includes('cpu_usage_user')) return 18;
  if (query.includes('cpu_usage_system')) return 12;
  if (query.includes('cpu_usage_iowait')) return 2;
  if (query.includes('mem_used_percent')) return 62;
  if (query.includes('mem_available')) return 5 * 1024 * 1024 * 1024;
  if (query.includes('mem_cached')) return 2 * 1024 * 1024 * 1024;
  if (query.includes('mem_buffered')) return 512 * 1024 * 1024;
  if (query.includes('cpu_usage_idle')) return 42;
  if (query.includes('disk_used_percent')) return 48;
  if (query.includes('processes_running')) return 9;
  if (query.includes('processes_sleeping')) return 386;
  if (query.includes('processes_blocked')) return 1;
  if (query.includes('processes_zombies')) return 0;
  if (query.includes('system_load1')) return 1.42;
  if (query.includes('system_load5')) return 1.26;
  if (query.includes('system_load15')) return 1.18;
  if (query.includes('uptime') || query.includes('Uptime')) return 86400 * 18;
  if (query.includes('connected_clients') || query.includes('connections') || query.includes('Connections') || query.includes('connection_count')) return 64;
  if (query.includes('blocked') || query.includes('rejected') || query.includes('error') || query.includes('Error') || query.includes('failed')) return unit === 'percent' ? 1.2 : 2;
  if (query.includes('hit') || query.includes('Hit')) return unit === 'percent' ? 96.5 : 280;
  if (query.includes('miss') || query.includes('Miss')) return unit === 'percent' ? 3.5 : 12;
  if (query.includes('memory') || query.includes('Memory') || query.includes('mem_')) return unit === 'percent' ? 62 : 6 * 1024 * 1024 * 1024;
  if (query.includes('heap')) return unit === 'percent' ? 57 : 2 * 1024 * 1024 * 1024;
  if (query.includes('thread') || query.includes('Thread')) return unit === 'percent' ? 41 : 48;
  if (query.includes('queue') || query.includes('Queue')) return 38;
  if (query.includes('request') || query.includes('Request') || query.includes('ReqPerSec')) return unit === 'percent' ? 98 : 360;
  if (query.includes('bytes') || query.includes('Bytes') || query.includes('net_')) return unit === 'percent' ? 54 : 420 * 1024;
  if (query.includes('disk') || query.includes('Disk')) return unit === 'percent' ? 52 : 11 * 1024 * 1024 * 1024;
  if (query.includes('status') || query.includes('Status') || query.includes('health') || query.includes('up{')) return 1;
  if (query.includes('prometheus_remote_write_kube_node_status_condition')) return 1;
  if (query.includes('prometheus_remote_write_kube_pod_status_phase')) return 1;
  if (query.includes('CrashLoopBackOff')) return 0;
  if (query.includes('restarts')) return 2;
  if (query.includes('deployment_status_replicas_unavailable')) return 0;
  if (query.includes('daemonset_status_number_unavailable')) return 0;
  if (query.includes('statefulset_status_replicas_ready') && query.includes('<')) return 0;
  if (query.includes('deployment_status_replicas_available') || query.includes('statefulset_status_replicas_ready') || query.includes('daemonset_status_number_available')) return 96;
  if (query.includes('kube_node_status_allocatable') && query.includes('resource="cpu"')) return 12;
  if (query.includes('kube_pod_container_resource_requests') && query.includes('resource="cpu"')) return 4.2;
  if (query.includes('container_cpu_usage_seconds_total')) return query.includes('100 *') ? 36 : 1.8;
  if (query.includes('kube_node_status_allocatable') && query.includes('resource="memory"')) return 32 * 1024 * 1024 * 1024;
  if (query.includes('kube_pod_container_resource_requests') && query.includes('resource="memory"')) return 12 * 1024 * 1024 * 1024;
  if (query.includes('container_memory_working_set_bytes')) return unit === 'percent' ? 58 : 9 * 1024 * 1024 * 1024;
  if (query.includes('container_network_receive_bytes_total')) return 680 * 1024;
  if (query.includes('container_network_transmit_bytes_total')) return 520 * 1024;
  if (query.includes('container_fs_reads_total')) return 84;
  if (query.includes('container_fs_writes_total')) return 61;
  if (query.includes('prometheus_remote_write_mem_used') && query.includes('prometheus_remote_write_mem_total')) return 58;
  if (query.includes('prometheus_remote_write_disk_used') && query.includes('prometheus_remote_write_disk_total')) return 47;
  if (query.includes('namespace')) return 6;
  if (query.includes('pod')) return 24;
  if (query.includes('node')) return 3;
  if (query.includes('deployment')) return 8;
  if (query.includes('daemonset')) return 3;
  if (query.includes('statefulset')) return 4;
  if (query.includes('cpu') && unit === 'none') return 1.8;
  if (unit === 'percent') return 54;
  if (unit === 'bytes') return 8 * 1024 * 1024 * 1024;
  if (unit === 'byteps') return 320 * 1024;
  if (unit === 'ms') return 38;
  if (unit === 'cps') return 420;
  if (unit === 'counts') return 128;
  return 42;
};

const metricSeries = (
  metric: Record<string, string>,
  base: number,
  unit: string
) => ({
  metric,
  values: buildValues(base, unit)
});

const unescapePromRegexValue = (value: string) =>
  value.replace(/\\\\/g, '\\').replace(/\\([\\^$.*+?()[\]{}|"-])/g, '$1');

const parseLabels = (query = '') => {
  const labels: Record<string, string> = {};
  const matcher = /([a-zA-Z_][\w]*)=~"([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(query))) {
    labels[match[1]] = unescapePromRegexValue(match[2]).split('|')[0] || '';
  }
  return labels;
};

const buildMetricLabels = (query = '') => {
  const labels = parseLabels(query);
  const instanceId = labels.instance_id || 'orbstack';
  return {
    instance_id: instanceId,
    host: labels.host || instanceId || 'mac',
    node: labels.node || (instanceId === 'orbstack' ? 'orb-node-1' : instanceId),
    pod: labels.pod || (instanceId === 'orbstack' ? 'demo-pod-1' : instanceId),
    device: labels.device || '/dev/disk1',
    name: labels.name || 'disk0',
    interface: labels.interface || 'en0',
    container: labels.container || 'app'
  };
};

const queryRange = (params: QueryRangeParams = {}) => {
  const query = params.query || '';
  const unit = params.source_unit || 'none';
  const baseLabels = buildMetricLabels(query);

  if (query.includes(' by (phase)')) {
    return {
      data: {
        result: [
          metricSeries({ ...baseLabels, phase: 'Running' }, 21, 'none'),
          metricSeries({ ...baseLabels, phase: 'Pending' }, 1, 'none'),
          metricSeries({ ...baseLabels, phase: 'Succeeded' }, 2, 'none')
        ]
      }
    };
  }

  if (query.includes('topk')) {
    const label = query.includes('container_label_io_kubernetes_pod_namespace')
      ? 'container_label_io_kubernetes_pod_namespace'
      : query.includes('pod')
        ? 'pod'
        : 'node';
    return {
      data: {
        result: Array.from({ length: 5 }, (_, index) =>
          metricSeries(
            {
              ...baseLabels,
              node: `orb-node-${index + 1}`,
              pod: `demo-pod-${index + 1}`,
              [label]: label === 'container_label_io_kubernetes_pod_namespace' ? `namespace-${index + 1}` : label === 'pod' ? `demo-pod-${index + 1}` : `orb-node-${index + 1}`
            },
            inferBaseValue(query, unit) * (1 - index * 0.13),
            unit
          )
        )
      }
    };
  }

  return {
    data: {
      result: [
        metricSeries(
          baseLabels,
          inferBaseValue(query, unit),
          unit
        )
      ]
    }
  };
};

const objectInstances: Record<string, Array<Record<string, unknown>>> = {
  host: [{ instance_id: 'mac', instance_name: 'mac', host: '127.0.0.1', instance_id_values: ['mac'], interval: 60 }],
  website: [{ instance_id: 'blueking-lite', instance_name: 'BlueKing Lite', url: 'http://127.0.0.1:3000', instance_id_values: ['blueking-lite'], interval: 60 }],
  ping: [{ instance_id: 'local-ping', instance_name: '127.0.0.1', host: '127.0.0.1', instance_id_values: ['local-ping'], interval: 60 }],
  tcp: [{ instance_id: 'local-tcp', instance_name: '127.0.0.1:3000', host: '127.0.0.1', port: 3000, instance_id_values: ['local-tcp'], interval: 60 }],
  mysql: [{ instance_id: 'mysql-primary', instance_name: 'mysql-primary', host: '127.0.0.1', port: 3306, instance_id_values: ['mysql-primary'], interval: 60 }],
  redis: [{ instance_id: 'redis-cache', instance_name: 'redis-cache', host: '127.0.0.1', port: 6379, instance_id_values: ['redis-cache'], interval: 60 }],
  mongodb: [{ instance_id: 'mongodb-rs0', instance_name: 'mongodb-rs0', host: '127.0.0.1', port: 27017, instance_id_values: ['mongodb-rs0'], interval: 60 }],
  mssql: [{ instance_id: 'mssql-main', instance_name: 'mssql-main', host: '127.0.0.1', port: 1433, instance_id_values: ['mssql-main'], interval: 60 }],
  postgres: [{ instance_id: 'postgres-primary', instance_name: 'postgres-primary', host: '127.0.0.1', port: 5432, instance_id_values: ['postgres-primary'], interval: 60 }],
  elasticsearch: [{ instance_id: 'es-cluster', instance_name: 'es-cluster', host: '127.0.0.1', port: 9200, instance_id_values: ['es-cluster'], interval: 60 }],
  nginx: [{ instance_id: 'nginx-edge', instance_name: 'nginx-edge', host: '127.0.0.1', port: 80, instance_id_values: ['nginx-edge'], interval: 60 }],
  docker: [{ instance_id: 'docker-local', instance_name: 'docker-local', host: '127.0.0.1', instance_id_values: ['docker-local'], interval: 60 }],
  activemq: [{ instance_id: 'activemq-main', instance_name: 'activemq-main', host: '127.0.0.1', port: 8161, instance_id_values: ['activemq-main'], interval: 60 }],
  apache: [{ instance_id: 'apache-web', instance_name: 'apache-web', host: '127.0.0.1', port: 8080, instance_id_values: ['apache-web'], interval: 60 }],
  consul: [{ instance_id: 'consul-server', instance_name: 'consul-server', host: '127.0.0.1', port: 8500, instance_id_values: ['consul-server'], interval: 60 }],
  rabbitmq: [{ instance_id: 'rabbitmq-main', instance_name: 'rabbitmq-main', host: '127.0.0.1', port: 15672, instance_id_values: ['rabbitmq-main'], interval: 60 }],
  ibmmq: [{ instance_id: 'ibmmq-qm1', instance_name: 'ibmmq-qm1', host: '127.0.0.1', port: 9443, instance_id_values: ['ibmmq-qm1'], interval: 60 }],
  tomcat: [{ instance_id: 'tomcat-app', instance_name: 'tomcat-app', host: '127.0.0.1', port: 8080, instance_id_values: ['tomcat-app'], interval: 60 }],
  zookeeper: [{ instance_id: 'zookeeper-main', instance_name: 'zookeeper-main', host: '127.0.0.1', port: 2181, instance_id_values: ['zookeeper-main'], interval: 60 }],
  'k8s-cluster': [{ instance_id: 'orbstack', instance_name: 'orbstack', instance_id_values: ['orbstack'], interval: 60 }],
  'k8s-node': [{ instance_id: 'orb-node-1', instance_name: 'orb-node-1', instance_id_values: ['orbstack', 'orb-node-1'], interval: 60 }],
  'k8s-pod': [{ instance_id: 'demo-pod-1', instance_name: 'demo-pod-1', instance_id_values: ['orbstack', 'demo-pod-1'], interval: 60 }]
};

const inferObjectKey = (url: string) => {
  const matched = url.match(/monitor_instance\/([^/]+)\/list/);
  return matched?.[1] || '';
};

const get = async (url: string, config?: AxiosRequestConfig) => {
  if (url.includes('/monitor/api/metrics_instance/query_range/') || url.includes('/monitor/api/metrics_instance/query_by_instance/')) {
    return queryRange((config?.params || {}) as QueryRangeParams);
  }

  if (url.includes('/monitor/api/monitor_instance/') && url.includes('/list/')) {
    const key = inferObjectKey(url);
    return { results: objectInstances[key] || [{ instance_id: key || 'demo', instance_name: key || 'demo', instance_id_values: [key || 'demo'], interval: 60 }] };
  }

  if (url.includes('/monitor/api/unit/list')) {
    return [];
  }

  return [];
};

const post = async (url: string, data?: Record<string, unknown>) => {
  if (url.includes('/monitor/api/monitor_instance/') && url.includes('/search/')) {
    const key = inferObjectKey(url.replace('/search/', '/list/'));
    return { results: objectInstances[key] || [] };
  }

  if (url.includes('/monitor/api/metrics_instance/query_by_instance/')) {
    return queryRange((data || {}) as QueryRangeParams);
  }

  return {};
};
const put = async () => ({});
const del = async () => ({});
const patch = async () => ({});

export const createStorybookMonitorApiClient = () => ({
  get,
  post,
  put,
  del,
  patch,
  isLoading: false
});

export const isSilentRequestError = () => false;
export class HandledRequestError extends Error {}
const useApiClient = createStorybookMonitorApiClient;
export default useApiClient;

const buildApiResponse = (data: unknown) => JSON.stringify({
  result: true,
  message: 'ok',
  data
});

const parseQueryParams = (url: string) => {
  const parsed = new URL(url, globalThis.location?.origin || 'http://127.0.0.1:6006');
  return Object.fromEntries(parsed.searchParams.entries());
};

const resolveMockData = async (method: string, url: string, body?: string) => {
  const parsed = new URL(url, globalThis.location?.origin || 'http://127.0.0.1:6006');
  const pathname = parsed.pathname.replace(/^\/api\/proxy/, '');

  if (pathname.startsWith('/monitor/api/')) {
    if (method === 'POST') {
      return post(pathname, body ? JSON.parse(body) : undefined);
    }
    return get(pathname, { params: parseQueryParams(url) });
  }

  if (pathname === '/core/api/login_info/') {
    return { username: 'admin', display_name: 'admin', roles: ['admin'] };
  }

  if (pathname === '/core/api/get_user_menus/') {
    return [];
  }

  if (pathname === '/core/api/get_client/') {
    return [];
  }

  if (pathname === '/core/api/get_bk_settings/') {
    return {};
  }

  if (pathname === '/console_mgmt/user_app_sets/current_user_apps/') {
    return [];
  }

  return undefined;
};

export const installMonitorDashboardRequestInterceptor = () => {
  const target = globalThis as any;
  if (target.__monitorDashboardStorybookInterceptorInstalled || typeof target.XMLHttpRequest !== 'function') return;
  target.__monitorDashboardStorybookInterceptorInstalled = true;

  const NativeXMLHttpRequest = target.XMLHttpRequest;

  class StorybookXMLHttpRequest {
    private native = new NativeXMLHttpRequest();
    private method = 'GET';
    private url = '';
    private requestHeaders: Record<string, string> = {};
    private listeners: Record<string, Array<(...args: any[]) => void>> = {};

    readyState = 0;
    status = 0;
    statusText = '';
    responseText = '';
    response: any = '';
    responseType = '';
    timeout = 0;
    withCredentials = false;
    onreadystatechange: null | (() => void) = null;
    onload: null | (() => void) = null;
    onerror: null | (() => void) = null;
    ontimeout: null | (() => void) = null;

    open(method: string, url: string) {
      this.method = method.toUpperCase();
      this.url = url;
      this.readyState = 1;
      this.onreadystatechange?.();
      if (!this.shouldIntercept()) {
        this.native.open(method, url);
      }
    }

    setRequestHeader(name: string, value: string) {
      this.requestHeaders[name] = value;
      if (!this.shouldIntercept()) {
        this.native.setRequestHeader(name, value);
      }
    }

    getAllResponseHeaders() {
      return this.shouldIntercept() ? 'content-type: application/json\r\n' : this.native.getAllResponseHeaders();
    }

    getResponseHeader(name: string) {
      return this.shouldIntercept() && name.toLowerCase() === 'content-type'
        ? 'application/json'
        : this.native.getResponseHeader(name);
    }

    addEventListener(type: string, listener: (...args: any[]) => void) {
      if (!this.listeners[type]) this.listeners[type] = [];
      this.listeners[type].push(listener);
      if (!this.shouldIntercept()) {
        this.native.addEventListener(type, listener as EventListener);
      }
    }

    removeEventListener(type: string, listener: (...args: any[]) => void) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener);
      if (!this.shouldIntercept()) {
        this.native.removeEventListener(type, listener as EventListener);
      }
    }

    abort() {
      if (!this.shouldIntercept()) this.native.abort();
    }

    send(body?: string) {
      if (!this.shouldIntercept()) {
        this.native.onreadystatechange = () => {
          this.readyState = this.native.readyState;
          this.status = this.native.status;
          this.statusText = this.native.statusText;
          this.responseText = this.native.responseText;
          this.response = this.native.response;
          this.onreadystatechange?.();
        };
        this.native.onload = () => this.onload?.();
        this.native.onerror = () => this.onerror?.();
        this.native.ontimeout = () => this.ontimeout?.();
        this.native.timeout = this.timeout;
        this.native.withCredentials = this.withCredentials;
        this.native.responseType = this.responseType as XMLHttpRequestResponseType;
        Object.entries(this.requestHeaders).forEach(([name, value]) => this.native.setRequestHeader(name, value));
        this.native.send(body);
        return;
      }

      void resolveMockData(this.method, this.url, body).then((data) => {
        this.readyState = 4;
        this.status = data === undefined ? 404 : 200;
        this.statusText = data === undefined ? 'Not Found' : 'OK';
        this.responseText = data === undefined ? '' : buildApiResponse(data);
        this.response = this.responseType === 'json' ? JSON.parse(this.responseText) : this.responseText;
        this.onreadystatechange?.();
        this.onload?.();
        (this.listeners.load || []).forEach((listener) => listener.call(this));
        (this.listeners.loadend || []).forEach((listener) => listener.call(this));
      });
    }

    private shouldIntercept() {
      return this.url.includes('/api/proxy/monitor/api/') ||
        this.url.includes('/api/proxy/core/api/') ||
        this.url.includes('/api/proxy/console_mgmt/user_app_sets/current_user_apps/');
    }
  }

  target.XMLHttpRequest = StorybookXMLHttpRequest as any;
};
