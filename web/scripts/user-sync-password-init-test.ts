/**
 * 用户同步-本地密码初始化前端契约测试
 *
 * 验证:
 * 1. i18n key 中英文双语都覆盖(防止回退硬编码)
 * 2. 类型定义 PasswordInitConfig 在 user-sync types 中导出
 * 3. 前端 payload 与表单路径统一使用 platform_config.password_init
 *
 * 运行: cd web && npx tsx scripts/user-sync-password-init-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(__dirname, '..');

const REQUIRED_KEYS = [
  'sectionTitle',
  'modeNone',
  'modeUniform',
  'modeRandom',
  'modeNoneHint',
  'modeUniformHint',
  'modeRandomHint',
  'uniformPasswordLabel',
  'uniformPasswordPlaceholder',
  'uniformPasswordKeepHint',
  'emailChannelLabel',
  'emailChannelPlaceholder',
  'uniformWarning',
];

const zhPath = resolve(ROOT, 'src/app/system-manager/locales/zh.json');
const enPath = resolve(ROOT, 'src/app/system-manager/locales/en.json');
const typesPath = resolve(ROOT, 'src/app/system-manager/types/user-sync.ts');
const utilsPath = resolve(ROOT, 'src/app/system-manager/utils/userSyncUtils.ts');
const sectionPath = resolve(ROOT, 'src/app/system-manager/components/user/user-sync/PasswordInitSection.tsx');
const mappingUtilsPath = resolve(ROOT, 'src/app/system-manager/utils/userSyncPageUtils.ts');
const createModalPath = resolve(ROOT, 'src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx');
const configModalPath = resolve(ROOT, 'src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx');
const configFieldsPath = resolve(ROOT, 'src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx');
const userSyncApiPath = resolve(ROOT, 'src/app/system-manager/api/user-sync/index.ts');

const zh = JSON.parse(readFileSync(zhPath, 'utf8'));
const en = JSON.parse(readFileSync(enPath, 'utf8'));

const zhPI = zh?.system?.user?.userSyncPage?.passwordInit ?? {};
const enPI = en?.system?.user?.userSyncPage?.passwordInit ?? {};

let failed = 0;

for (const key of REQUIRED_KEYS) {
  if (!zhPI[key]) {
    console.error(`✗ zh 缺 key: system.user.userSyncPage.passwordInit.${key}`);
    failed++;
  }
  if (!enPI[key]) {
    console.error(`✗ en 缺 key: system.user.userSyncPage.passwordInit.${key}`);
    failed++;
  }
}

const typesSource = readFileSync(typesPath, 'utf8');
const utilsSource = readFileSync(utilsPath, 'utf8');
const sectionSource = readFileSync(sectionPath, 'utf8');
const mappingUtilsSource = readFileSync(mappingUtilsPath, 'utf8');
const createModalSource = readFileSync(createModalPath, 'utf8');
const configModalSource = readFileSync(configModalPath, 'utf8');
const configFieldsSource = readFileSync(configFieldsPath, 'utf8');
const userSyncApiSource = readFileSync(userSyncApiPath, 'utf8');
if (!typesSource.includes('PasswordInitConfig')) {
  console.error('✗ types/user-sync.ts 未导出 PasswordInitConfig 类型');
  failed++;
}
if (!typesSource.includes('PasswordInitMode')) {
  console.error('✗ types/user-sync.ts 未导出 PasswordInitMode 类型');
  failed++;
}
if (!typesSource.includes("'uniform'")) {
  console.error('✗ PasswordInitMode 应包含 uniform 字面量');
  failed++;
}
if (!typesSource.includes("'random'")) {
  console.error('✗ PasswordInitMode 应包含 random 字面量');
  failed++;
}
if (!typesSource.includes("'none'")) {
  console.error('✗ PasswordInitMode 应包含 none 字面量');
  failed++;
}
if (!typesSource.includes('platform_config?: PlatformConfig')) {
  console.error('✗ UserSyncSource 应暴露 platform_config?: PlatformConfig');
  failed++;
}
if (!utilsSource.includes('platform_config')) {
  console.error('✗ userSyncUtils payload builder 应提交 platform_config');
  failed++;
}
if (utilsSource.includes('password_init_config')) {
  console.error('✗ userSyncUtils 不应再提交 password_init_config 顶层字段');
  failed++;
}
if (!sectionSource.includes("['platform_config', 'password_init']")) {
  console.error('✗ PasswordInitSection 表单路径应为 platform_config.password_init');
  failed++;
}
if (!sectionSource.includes("form.setFieldValue(FIELD_PATH, { mode: 'none' })")) {
  console.error('✗ PasswordInitSection 默认 none 必须显式写入 form,避免提交空 platform_config');
  failed++;
}
if (sectionSource.includes("['password_init_config']")) {
  console.error('✗ PasswordInitSection 不应再使用 password_init_config 顶层路径');
  failed++;
}
if (!sectionSource.includes('uniform_password_configured')) {
  console.error('✗ PasswordInitSection 应支持已配置统一密码的脱敏编辑状态');
  failed++;
}
if (!typesSource.includes('uniform_password_configured')) {
  console.error('✗ PasswordInitConfig 应声明统一密码已配置标记');
  failed++;
}
if (!mappingUtilsSource.includes('validateRequiredUserMapping')) {
  console.error('✗ 字段映射工具应导出用户名必填校验');
  failed++;
}
if (!createModalSource.includes('validateRequiredUserMapping(mappingRows)')) {
  console.error('✗ 新增同步源弹窗应校验用户名映射');
  failed++;
}
if (!configModalSource.includes('validateRequiredUserMapping(mappingRows)')) {
  console.error('✗ 编辑同步源弹窗应校验用户名映射');
  failed++;
}
if (!createModalSource.includes('message.warning(mappingErrorMessage)')) {
  console.error('✗ 新增同步源弹窗应提示用户名映射缺失');
  failed++;
}
if (!configModalSource.includes('message.warning(mappingErrorMessage)')) {
  console.error('✗ 编辑同步源弹窗应提示用户名映射缺失');
  failed++;
}
if (!userSyncApiSource.includes('checkRootGroupNameAvailable')) {
  console.error('✗ 用户同步 API 应提供根组织名称实时校验');
  failed++;
}
if (!createModalSource.includes('validateRootGroupNameAvailable')) {
  console.error('✗ 新增同步源弹窗应实时校验根组织名称');
  failed++;
}
if (!configFieldsSource.includes("invalid={row.platformField === 'username' && Boolean(mappingError)}")) {
  console.error('✗ 用户名映射缺失时应标记对应输入框');
  failed++;
}
if (configFieldsSource.includes('{mappingError ? (')) {
  console.error('✗ 用户名映射缺失时不应显示映射区域底部提示');
  failed++;
}
if (configFieldsSource.includes('{error ? <div')) {
  console.error('✗ 用户名映射校验错误不应撑高单行字段映射布局');
  failed++;
}

if (failed === 0) {
  console.log(`✓ ${REQUIRED_KEYS.length} i18n keys 全量覆盖 + 类型定义导出`);
  process.exit(0);
} else {
  console.error(`✗ ${failed} 项缺失`);
  process.exit(1);
}
