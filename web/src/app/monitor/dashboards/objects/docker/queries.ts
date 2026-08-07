/** Docker 容器资源 TopN */
export const DOCKER_TOP_N = 8;

interface GuideItem {
  label: string;
  detail: string;
}

export interface DockerTopQuery {
  key: string;
  title: string;
  unit: string;
  color: string;
  query: string;
  labelKeys: string[];
  guide: GuideItem[];
}

export const DOCKER_TOP_QUERIES: DockerTopQuery[] = [
  {
    key: 'cpu',
    title: '容器 CPU Top',
    unit: 'percent',
    color: '#2f6bff',
    labelKeys: ['container_name'],
    query: `topk(${DOCKER_TOP_N}, max by (container_name) (docker_container_cpu_usage_percent{__$labels__}))`,
    guide: [{ label: 'CPU 排行', detail: '各容器 CPU 使用率，定位占用最高的容器。' }]
  },
  {
    key: 'mem',
    title: '容器内存 Top',
    unit: 'percent',
    color: '#8a5cff',
    labelKeys: ['container_name'],
    query: `topk(${DOCKER_TOP_N}, max by (container_name) (docker_container_mem_usage_percent{__$labels__}))`,
    guide: [{ label: '内存排行', detail: '各容器内存使用率，定位内存压力最大的容器。' }]
  }
];
