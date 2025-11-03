#!/usr/bin/env node
/**
 * 跨平台 Android 构建入口脚本
 * 自动检测操作系统并调用对应的构建脚本
 */

import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 获取命令行参数
const args = process.argv.slice(2).join(' ');

// 检测操作系统
const isWindows = process.platform === 'win32';

// 选择对应的脚本
const script = isWindows
    ? path.join('scripts', 'android-build.bat')
    : path.join('scripts', 'android-build.sh');

const command = isWindows
    ? `${script} ${args}`
    : `bash ${script} ${args}`;

try {
    // 执行构建脚本
    execSync(command, { stdio: 'inherit', cwd: process.cwd() });
} catch (error) {
    process.exit(error.status || 1);
}
