import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  createModelIconOptions,
  DEFAULT_MODEL_ICON_NAME,
  resolveModelIconReference,
} from '../src/app/cmdb/utils/modelIconResolver';

const loadIcons = (directory: string) =>
  readdirSync(resolve(process.cwd(), directory))
    .filter((filename) => filename.endsWith('.svg'))
    .map((filename) => {
      const url = filename.replace(/\.svg$/, '');
      return {
        key: url.split('_')[0],
        describe: url.split('_')[1],
        url,
      };
    });

const standardIcons = loadIcons('public/assets/icons');
const realisticIcons = loadIcons('public/assets/icons-realistic');
const standardIconNames = new Set(standardIcons.map((item) => item.url));
const realisticIconNames = new Set(realisticIcons.map((item) => item.url));
const iconOptions = createModelIconOptions(standardIcons, realisticIcons);

iconOptions.forEach((option) => {
  assert.equal(
    resolveModelIconReference(
      { icn: option.value, model_id: option.key },
      standardIcons,
      realisticIcons
    ),
    option.value,
    `精确图标引用应保持选择结果: ${option.value}`
  );
});

assert.equal(
  realisticIconNames.has(DEFAULT_MODEL_ICON_NAME),
  true,
  '默认模型图标必须存在于写实图标目录'
);

const certificateOptions = iconOptions.filter(
  (item) => item.url === 'cc-certificate_证书'
);
assert.deepEqual(
  certificateOptions.map((item) => item.value),
  [
    'icons-realistic/cc-certificate_证书',
    'icons/cc-certificate_证书',
  ],
  '同文件名的写实和普通图标应分别提供，并保持写实图标在前'
);

certificateOptions.forEach((selectedCertificate) => {
  const previewCertificate = resolveModelIconReference(
    { icn: selectedCertificate.value, model_id: 'certificate' },
    standardIcons,
    realisticIcons
  );
  assert.equal(
    previewCertificate,
    selectedCertificate.value,
    '新选择的精确图标引用应原样解析'
  );
  assert.deepEqual(
    readFileSync(resolve('public/assets', `${previewCertificate}.svg`)),
    readFileSync(resolve('public/assets', `${selectedCertificate.value}.svg`)),
    '选择器选中的图标应与外层弹窗预览一致'
  );
});

const consulOption = iconOptions.find(
  (item) => item.url === 'cc-consul_Consul'
);
assert.ok(consulOption, '选择器应保留普通目录独有图标');
assert.equal(
  consulOption.value,
  'icons/cc-consul_Consul',
  '写实目录缺失时应使用普通图标'
);
assert.equal(
  standardIconNames.has('cc-consul_Consul') &&
    !realisticIconNames.has('cc-consul_Consul'),
  true,
  '测试图标应只存在于普通图标目录'
);

assert.equal(
  resolveModelIconReference(
    { icn: 'icon-cc-mysql', model_id: 'custom_mysql' },
    standardIcons,
    realisticIcons
  ),
  'icons-realistic/cc-mysql_MySQL',
  '历史 icon- 短 key 应优先解析到写实图标'
);

assert.equal(
  resolveModelIconReference(
    { icn: 'icon-cc-consul', model_id: 'custom_consul' },
    standardIcons,
    realisticIcons
  ),
  'icons/cc-consul_Consul',
  '历史短 key 在写实目录缺失时应使用普通图标'
);

assert.equal(
  resolveModelIconReference(
    { icn: 'icons/cc-certificate_证书', model_id: 'certificate' },
    standardIcons,
    realisticIcons
  ),
  'icons/cc-certificate_证书',
  '精确指定普通图标时不应自动切换到写实版本'
);

assert.equal(
  resolveModelIconReference(
    { icn: '', model_id: 'switch' },
    standardIcons,
    realisticIcons
  ),
  'icons-realistic/cc-switch2_交换机',
  '未配置图标时应按写实优先解析内置模型映射'
);

assert.equal(
  resolveModelIconReference(
    { icn: 'not-exists', model_id: 'not-exists' },
    standardIcons,
    realisticIcons
  ),
  `icons-realistic/${DEFAULT_MODEL_ICON_NAME}`,
  '两个目录都找不到时应回退默认图标'
);

console.log('CMDB model icon tests passed');
