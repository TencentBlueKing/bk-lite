import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const webRoot = resolve(import.meta.dirname, '..');
const readSource = (relativePath: string) =>
  readFileSync(resolve(webRoot, relativePath), 'utf8');

const installSource = readSource(
  'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installConfig/index.tsx'
);
const uninstallSource = readSource(
  'src/app/node-manager/(pages)/cloudregion/node/controllerUninstall/index.tsx'
);
const certificateFieldSource = readSource(
  'src/app/node-manager/components/winrm-certificate-validation-field/index.tsx'
);
const zhLocale = JSON.parse(
  readSource('src/app/node-manager/locales/zh.json')
) as {
  'node-manager': { cloudregion: { node: Record<string, string> } };
};
const zhNodeMessages = zhLocale['node-manager'].cloudregion.node;

assert.doesNotMatch(
  installSource,
  /setWinrmCertValidation\(true\)/,
  'Windows 安装配置切换时不得重新开启证书校验'
);
assert.doesNotMatch(
  installSource,
  /createInfoItem\([^\n]+,\s*true\)/,
  'Windows 安装配置重建节点行时不得写入开启证书校验'
);
assert.doesNotMatch(
  `${uninstallSource}\n${certificateFieldSource}`,
  /checkedChildren|unCheckedChildren/,
  '证书校验说明不得塞入 Switch 内部导致控件被长文案撑宽'
);
assert.doesNotMatch(
  zhNodeMessages.windowsRemoteInstallDes,
  /默认校验证书/,
  'Windows 远程安装说明必须与默认关闭证书校验保持一致'
);

console.log('Node Manager WinRM certificate defaults and UI contract passed.');
