#!/usr/bin/env node

const { execSync } = require('child_process');

const startTime = Date.now();

console.log('\n🚀 开始构建...\n');
console.log(`⏰ 开始时间: ${new Date(startTime).toLocaleString('zh-CN')}\n`);

try {
  // 执行 next build
  execSync('next build', {
    stdio: 'inherit',
    env: process.env,
  });

  const endTime = Date.now();
  const duration = ((endTime - startTime) / 1000).toFixed(2);
  const minutes = Math.floor(duration / 60);
  const seconds = (duration % 60).toFixed(2);

  console.log('\n✅ 构建完成！\n');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log(`⏱️  总耗时: ${minutes > 0 ? `${minutes}分${seconds}秒` : `${seconds}秒`}`);
  console.log(`⏰ 结束时间: ${new Date(endTime).toLocaleString('zh-CN')}`);
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
} catch (error) {
  const endTime = Date.now();
  const duration = ((endTime - startTime) / 1000).toFixed(2);

  console.error('\n❌ 构建失败！\n');
  console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.error(`⏱️  失败前耗时: ${duration}秒`);
  console.error(`⏰ 失败时间: ${new Date(endTime).toLocaleString('zh-CN')}`);
  console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

  process.exit(1);
}
