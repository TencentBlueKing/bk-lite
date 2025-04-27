const fs = require('fs');
const path = require('path');

// 0. 调试日志
console.log('=== 开始生成 tsconfig.lint.json ===');

// 1. 加载环境变量
require('dotenv').config({ path: path.join(__dirname, '../.env') });
console.log('process.env.NEXTAPI_INSTALL_APP', process.env.NEXTAPI_INSTALL_APP);
const activeApps = process.env.NEXTAPI_INSTALL_APP?.split(',')
  .map(app => app.trim().replace(/[()]/g, '')) || ['system-manager'];
console.log('激活的应用:', activeApps);

// 2. 生成 include 规则
const commonDirs = [
  'next-auth.d.ts',
  '.next/types/**/*.ts',
  'next.config.mjs',
  'src/app/(core)/**/*',
  'src/app/no-permission/**/*',
  'src/app/layout.tsx',
  'src/app/page.tsx',
  'src/app/no-found.tsx',
  'src/components/**/*',
  'src/constants/**/*',
  'src/context/**/*',
  'src/hooks/**/*',
  'src/stories/**/*',
  'src/utils/**/*',
  // 其他公共目录...
].filter(Boolean);

const appIncludes = activeApps.map(app => `src/app/${app}/**/*`);
const include = [...commonDirs, ...appIncludes, 'next-env.d.ts'];

// 3. 生成配置（不继承 include）
const tsconfig = {
  compilerOptions: require('../tsconfig.json').compilerOptions,
  include,
  exclude: ['node_modules']
};

// 4. 写入文件
const outputPath = path.join(__dirname, '../tsconfig.lint.json');
fs.writeFileSync(outputPath, JSON.stringify(tsconfig, null, 2));
console.log('✅ 生成配置到:', outputPath);
console.log('include 内容:', include);
