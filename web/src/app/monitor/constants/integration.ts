import { ObjectIconMap } from '@/app/monitor/types';

const CONNECTION_LIFETIME_UNITS: string[] = ['m'];

const TIMEOUT_UNITS: string[] = ['s'];

const NEED_TAGS_ENTRY_OBJECTS = [
  'Docker',
  'Cluster',
  'vCenter',
  'TCP',
  'SangforSCP'
];

const NODE_STATUS_MAP: ObjectIconMap = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray'
};

const OBJECT_NAME_TO_TYPE_MAP: Record<string, string> = {
  Docker: 'Container Management',
  Cluster: 'K8S',
  vCenter: 'VMWare',
  TCP: 'Tencent Cloud',
  SangforSCP: 'Cloud'
};

export {
  CONNECTION_LIFETIME_UNITS,
  TIMEOUT_UNITS,
  NEED_TAGS_ENTRY_OBJECTS,
  NODE_STATUS_MAP,
  OBJECT_NAME_TO_TYPE_MAP
};
