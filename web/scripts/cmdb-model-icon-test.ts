import assert from 'node:assert/strict';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  DEFAULT_MODEL_ICON_NAME,
  resolveModelIconName,
} from '../src/app/cmdb/utils/modelIconResolver';

const loadIcons = (directory: string) =>
  readdirSync(resolve(process.cwd(), directory))
    .filter((filename) => filename.endsWith('.svg'))
    .map((filename) => {
      const url = filename.replace(/\.svg$/, '');
      return { key: url.split('_')[0], url };
    });

const standardIconNames = new Set(
  loadIcons('public/assets/icons').map((item) => item.url)
);
const realisticIcons = loadIcons('public/assets/icons-realistic');
const realisticIconNames = new Set(realisticIcons.map((item) => item.url));

assert.equal(
  realisticIconNames.has(DEFAULT_MODEL_ICON_NAME),
  true,
  '默认模型图标必须存在于写实图标目录'
);

assert.equal(
  resolveModelIconName(
    { icn: 'icon-cc-mysql', model_id: 'custom_mysql' },
    realisticIcons
  ),
  'cc-mysql_MySQL',
  '历史 icon- 前缀应正确解析到存在的写实图标'
);

assert.equal(
  resolveModelIconName(
    { icn: '', model_id: 'switch' },
    realisticIcons
  ),
  'cc-switch2_交换机',
  '未配置图标时应使用内置模型映射'
);

assert.equal(
  standardIconNames.has('cc-consul_Consul') &&
    !realisticIconNames.has('cc-consul_Consul'),
  true,
  '测试图标应只存在于普通图标目录'
);

assert.equal(
  resolveModelIconName(
    { icn: 'cc-consul_Consul', model_id: 'custom_consul' },
    realisticIcons
  ),
  DEFAULT_MODEL_ICON_NAME,
  '写实目录中缺少配置图标时应回退默认图标'
);

assert.equal(
  resolveModelIconName(
    { icn: 'not-exists', model_id: 'not-exists' },
    realisticIcons
  ),
  DEFAULT_MODEL_ICON_NAME,
  '未知模型图标应回退默认写实图标'
);

console.log('CMDB model icon tests passed');
