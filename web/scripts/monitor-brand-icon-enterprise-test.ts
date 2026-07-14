import assert from 'node:assert/strict';
import { getPluginBrandIcon, getBrandLabel } from '../src/app/monitor/utils/common';

// 注入 window.__ENTERPRISE_BRANDS,验证 getPluginBrandIcon / getBrandLabel
// 拼接 CE_BRANDS 与 EE __ENTERPRISE_BRANDS 的策略。
// 失败降级:window undefined / __ENTERPRISE_BRANDS 缺失 → 拼接空数组,原状走纯 CE BRANDS。

type WindowShim = {
  __ENTERPRISE_BRANDS?: Array<{ match: RegExp; label: string; icon?: string }>;
};

const originalWindow = global.window;

const withWindow = (shim: WindowShim | undefined, run: () => void) => {
  if (shim === undefined) {
    (global as { window?: WindowShim }).window = undefined;
  } else {
    (global as { window?: WindowShim }).window = shim;
  }
  try {
    run();
  } finally {
    (global as { window?: WindowShim }).window = originalWindow;
  }
};

// 1. window undefined → 走纯 CE BRANDS;CE 无 storage brand,SYNOLOGY 命中失败。
withWindow(undefined, () => {
  assert.equal(
    getPluginBrandIcon('cisco'),
    'mm-cisco_思科',
    'window undefined 时仍命中 CE BRANDS(cisco)'
  );
  assert.equal(
    getPluginBrandIcon('SYNOLOGY'),
    undefined,
    'window undefined 且 CE 无 storage,SYNOLOGY 应 undefined'
  );
});

// 2. window.__ENTERPRISE_BRANDS 含 storage brand → 命中 storage。
withWindow(
  {
    __ENTERPRISE_BRANDS: [
      { match: /synology/i, label: 'Synology', icon: 'mm-synology_synology' },
    ],
  },
  () => {
    assert.equal(
      getPluginBrandIcon('SYNOLOGY'),
      'mm-synology_synology',
      '__ENTERPRISE_BRANDS 命中 synology'
    );
  }
);

// 3. window.__ENTERPRISE_BRANDS 空数组 → 走纯 CE BRANDS。
withWindow({ __ENTERPRISE_BRANDS: [] }, () => {
  assert.equal(
    getPluginBrandIcon('SYNOLOGY'),
    undefined,
    '__ENTERPRISE_BRANDS 空数组应等同缺失,SYNOLOGY 仍 undefined'
  );
});

// 4. CE BRANDS 优先:即使 EE 也注册了 cisco (故意 storage 版),仍走 CE 网络版。
withWindow(
  {
    __ENTERPRISE_BRANDS: [
      { match: /cisco/i, label: 'Cisco Storage', icon: 'mm-cisco_cisco' },
    ],
  },
  () => {
    assert.equal(
      getPluginBrandIcon('cisco'),
      'mm-cisco_思科',
      'CE BRANDS 在前,应返回网络版 cisco 而非 EE storage 版'
    );
  }
);

// 5. pluginName 为空 → undefined。
assert.equal(
  getPluginBrandIcon(''),
  undefined,
  '空 pluginName 应返回 undefined'
);

// 6. getBrandLabel 拼接 EE BRANDS 命中。
withWindow(
  {
    __ENTERPRISE_BRANDS: [{ match: /vtrak/i, label: 'Promise VTrak' }],
  },
  () => {
    assert.equal(getBrandLabel('VTRAK'), 'Promise VTrak', 'getBrandLabel 命中 EE vtrak');
  }
);

console.log('getPluginBrandIcon/getBrandLabel EE 拼接 validation passed');
