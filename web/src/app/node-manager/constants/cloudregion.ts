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

export { OPERATE_SYSTEMS, BATCH_FIELD_MAPS, DISPLAY_PLUGINS_COUNT };
