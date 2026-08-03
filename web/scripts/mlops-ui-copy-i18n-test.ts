import fs from 'node:fs';
import path from 'node:path';

type Locale = Record<string, unknown>;

const root = path.resolve(process.cwd());
const read = (relativePath: string) => fs.readFileSync(path.join(root, relativePath), 'utf8');
const get = (value: Locale, key: string): unknown => key.split('.').reduce<unknown>((current, segment) => (
  current && typeof current === 'object' ? (current as Locale)[segment] : undefined
), value);

const locales = ['zh', 'en'].map((locale) => JSON.parse(read(`src/app/mlops/locales/${locale}.json`)) as Locale);
const requiredKeys = [
  'datasets.logContent',
  'datasets.textContent',
  'datasets.label',
  'datasets.fileList',
  'traintask.datasetVersion',
  'traintask.selectDatasetVersion',
  'traintask.maxEvals',
  'traintask.inputMaxEvals',
  'traintask.maxEvalsTooltip',
  'traintask.maxEvalsPlaceholder',
  'algorithmConfig.defaultForm.basicConfig',
  'algorithmConfig.defaultForm.optimizationMetric',
  'algorithmConfig.defaultForm.searchSpace',
  'algorithmConfig.defaultForm.preprocessing',
  'algorithmConfig.defaultForm.featureEngineering',
  'algorithmConfig.algorithmNamePlaceholder',
  'algorithmConfig.displayNamePlaceholder',
  'algorithmConfig.scenarioDescriptionPlaceholder',
  'algorithmConfig.imagePlaceholder',
];

for (const key of requiredKeys) {
  for (const locale of locales) {
    if (typeof get(locale, key) !== 'string' || !get(locale, key)) {
      throw new Error(`Missing MLOps i18n key: ${key}`);
    }
  }
}

const sources = [
  'src/app/mlops/components/algorithm-config/AlgorithmConfigModal.tsx',
  'src/app/mlops/hooks/task/forms/useGenericDatasetForm.tsx',
  'src/app/mlops/components/annotation/tableContent.tsx',
  'src/app/mlops/components/annotation/aside/index.tsx',
].map(read).join('\n');

for (const text of ['基础配置', '优化指标', '数据集版本', '训练轮次', '日志内容', '文本内容', '标注', '文件列表']) {
  if (sources.includes(`'${text}'`) || sources.includes(`"${text}"`)) {
    throw new Error(`Hardcoded UI copy remains: ${text}`);
  }
}
