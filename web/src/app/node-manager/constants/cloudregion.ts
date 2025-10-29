import { SegmentedItem } from '@/app/node-manager/types';

const OPERATE_SYSTEMS: SegmentedItem[] = [
  {
    label: 'Linux',
    value: 'linux',
  },
  {
    label: 'Windows',
    value: 'windows',
  },
];

const BATCH_FIELD_MAPS: Record<string, string> = {
  os: 'operateSystem',
  organizations: 'organaziton',
  username: 'loginAccount',
  port: 'loginPort',
  password: 'loginPassword',
};

const DISPLAY_PLUGINS_COUNT = 4; // 最多展示几个插件

// 状态排序优先级
const STATUS_CODE_PRIORITY: Record<number, number> = {
  2: 1, // error
  12: 2, // warning
  10: 3, // processing
  4: 4, // stopped
  11: 5, // installed
  1: 6, // unknown
  0: 7, // success
};

export {
  OPERATE_SYSTEMS,
  BATCH_FIELD_MAPS,
  DISPLAY_PLUGINS_COUNT,
  STATUS_CODE_PRIORITY,
};
