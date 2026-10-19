const fs = require('fs');
const path = require('path');

// 0. Debug logs
console.log('=== Starting to generate tsconfig.lint.json ===');

// 1. Load environment variables
require('dotenv').config({ path: path.join(__dirname, '../.env') });
console.log('process.env.NEXTAPI_INSTALL_APP', process.env.NEXTAPI_INSTALL_APP);
const activeApps = process.env.NEXTAPI_INSTALL_APP?.split(',')
  .map(app => app.trim().replace(/[()]/g, '')) || ['system-manager'];
console.log('Active apps:', activeApps);

// 2. Generate include rules
const commonDirs = [
  'next-auth.d.ts',
  '.next/types/**/*.ts',
  'next.config.mjs',
  'src/app/(core)/**/*',
  'src/app/no-permission/**/*',
  'src/app/layout.tsx',
  'src/app/page.tsx',
  'src/app/no-found.tsx',
  'src/app/module-link/**/*',
  'src/components/**/*',
  'src/constants/**/*',
  'src/context/**/*',
  'src/hooks/**/*',
  'src/stories/**/*',
  'src/utils/**/*',
  // Other common directories...
].filter(Boolean);

const appIncludes = activeApps.map(app => `src/app/${app}/**/*`);
const include = [...commonDirs, ...appIncludes, 'next-env.d.ts'];

// 3. Generate configuration (without inheriting include)
const tsconfig = {
  compilerOptions: require('../tsconfig.json').compilerOptions,
  include,
  exclude: ['node_modules']
};

// 4. Write file
const outputPath = path.join(__dirname, '../tsconfig.lint.json');
fs.writeFileSync(outputPath, JSON.stringify(tsconfig, null, 2));
console.log('✅ Generated config to:', outputPath);
console.log('include content:', include);
