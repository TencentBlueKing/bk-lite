import { ObjectIconMap } from '@/app/monitor/types';

const CONNECTION_LIFETIME_UNITS: string[] = ['m'];

const TIMEOUT_UNITS: string[] = ['s'];

const NEED_TAGS_ENTRY_OBJECTS = ['Docker', 'Cluster', 'vCenter', 'TCP'];

const EXCLUDED_CHILD_OBJECTS = [
  'Pod',
  'Node',
  'Docker Container',
  'ESXI',
  'VM',
  'DataStorage',
  'CVM',
];

const NODE_STATUS_MAP: ObjectIconMap = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray',
};

export {
  CONNECTION_LIFETIME_UNITS,
  TIMEOUT_UNITS,
  NEED_TAGS_ENTRY_OBJECTS,
  EXCLUDED_CHILD_OBJECTS,
  NODE_STATUS_MAP,
};
