import { ObjectIconMap } from '@/app/monitor/types';

const CONNECTION_LIFETIME_UNITS: string[] = ['m'];

const TIMEOUT_UNITS: string[] = ['s'];

const NODE_STATUS_MAP: ObjectIconMap = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray'
};

export { CONNECTION_LIFETIME_UNITS, TIMEOUT_UNITS, NODE_STATUS_MAP };
