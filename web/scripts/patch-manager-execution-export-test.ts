import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const page = readFileSync(
  resolve(process.cwd(), 'src/app/patch-manager/(pages)/risk-execution/page.tsx'),
  'utf8',
);

const assertPresent = (pattern: RegExp, scope: string) => {
  if (!pattern.test(page)) throw new Error(`${scope} 缺少约束: ${pattern}`);
};
const assertAbsent = (pattern: RegExp, scope: string) => {
  if (pattern.test(page)) throw new Error(`${scope} 仍包含旧逻辑: ${pattern}`);
};

assertPresent(/import ExcelJS from 'exceljs'/, 'ExcelJS 真实工作簿导出');
assertPresent(/new ExcelJS\.Workbook\(\)/, '执行记录工作簿');
assertAbsent(/header:\s*'进度'/, '已隐藏易误解的进度列');
assertPresent(/header:\s*'主机'/, '每个风险项导出主机');
assertPresent(/header:\s*'补丁'/, '每个风险项导出补丁');
assertPresent(/header:\s*'安装状态'/, '安装步骤状态');
assertPresent(/header:\s*'重启状态'/, '重启步骤状态');
assertPresent(/header:\s*'验证状态'/, '验证步骤状态');
assertPresent(/page_size:\s*10000/, '导出全部遵循当前筛选而非当前页');
assertPresent(/application\/vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet/, 'XLSX MIME');
assertPresent(/\u6267\u884c\u8bb0\u5f55[^`]*\.xlsx/, '导出文件扩展名');
assertAbsent(/\u6267\u884c\u8bb0\u5f55[^`]*\.csv/, '会自动识别日期的 CSV 导出');

console.log('补丁执行记录导出格式约束通过');
