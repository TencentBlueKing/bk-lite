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
assertPresent(/patchManager\.execution\.exportHeaders/, '导出表头使用双语资源');
assertPresent(/installStatus:\s*stepMap\.install\s*\?\s*translate/, '安装步骤状态翻译');
assertPresent(/rebootStatus:\s*stepMap\.reboot\s*\?\s*translate/, '重启步骤状态翻译');
assertPresent(/verifyStatus:\s*stepMap\.verify\s*\?\s*translate/, '验证步骤状态翻译');
assertAbsent(/page_size:\s*10000/, '导出全部禁止一次拉取 page_size=10000');
assertPresent(/collectPagedItems/, '导出全部走分页收集');
assertPresent(/EXECUTION_EXPORT_LIST_PAGE_SIZE/, '导出全部使用分页常量');
assertPresent(/mapWithConcurrency/, '风险详情受控并发');
assertPresent(/EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY/, '风险详情并发上限');
assertPresent(/search:\s*appliedTaskSearch/, '导出全部保留当前搜索');
assertPresent(/task_type:\s*taskType/, '导出全部保留类型筛选');
assertPresent(/patchManager\.execution\.exportTruncated/, '超上限可观察提示');
assertAbsent(/\n\s*return Promise\.all\(\s*\n\s*\(task\.risk_items/, '禁止对全部风险项无界 Promise.all');
assertPresent(/application\/vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet/, 'XLSX MIME');
assertPresent(/patchManager\.execution\.records[^\n]*\.xlsx/, '导出文件双语名称与扩展名');
assertAbsent(/\u6267\u884c\u8bb0\u5f55[^`]*\.csv/, '会自动识别日期的 CSV 导出');

console.log('补丁执行记录导出格式约束通过');
