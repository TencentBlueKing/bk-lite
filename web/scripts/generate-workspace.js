#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

// Log for debugging
console.log('=== Generating pnpm-workspace.yaml ===');

// Load environment variables
require('dotenv').config({ path: path.join(__dirname, '../.env.local') });
const activeApps = process.env.NEXTAPI_INSTALL_APP?.split(',')
  .map(app => app.trim().replace(/[()]/g, '')) || ['*'];
console.log('Active applications:', activeApps);

// Generate workspace configuration
const workspaceConfig = [
  '# Auto-generated at ' + new Date().toISOString(),
  'packages:',
];

if (activeApps.includes('*')) {
  // Include all applications if wildcard is present
  workspaceConfig.push("  - 'src/app/*'");
} else {
  // Include specific applications
  activeApps.forEach(app => {
    workspaceConfig.push(`  - 'src/app/${app}'`);
  });
}

// Write to pnpm-workspace.yaml
const outputPath = path.join(__dirname, '../pnpm-workspace.yaml');
fs.writeFileSync(outputPath, workspaceConfig.join('\n'));
console.log('✅ Generated workspace configuration at:', outputPath);
console.log('Workspace content:\n', workspaceConfig.join('\n'));
