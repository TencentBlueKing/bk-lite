import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface DatasetVersionOption {
  label: string;
  value: string;
}

interface DatasetVersionRestoreParams {
  restoreVersion?: string | number | null;
  options: DatasetVersionOption[];
  allowRestore: boolean;
}

interface DatasetVersionRequestMatchParams {
  requestGeneration: number;
  currentGeneration: number;
  requestedDataset: number;
  currentDataset: number;
}

interface DatasetVersionSelectionFns {
  resolveDatasetVersionRestore: (params: DatasetVersionRestoreParams) => string | undefined;
  shouldApplyDatasetVersionResponse: (params: DatasetVersionRequestMatchParams) => boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const formPath = resolve(here, '../src/app/mlops/hooks/task/forms/useGenericDatasetForm.tsx');
const modalPath = resolve(here, '../src/app/mlops/components/TrainTaskModal.tsx');

const datasetAVersion = '101';
const datasetBOptions: DatasetVersionOption[] = [{ label: 'B-v1', value: '201' }];
const datasetAOptions: DatasetVersionOption[] = [{ label: 'A-v1', value: datasetAVersion }];

function legacyUnconditionalRestore(params: DatasetVersionRestoreParams): string | undefined {
  // 当前 renderOptions：if (formData?.dataset_version) 无条件 setFieldsValue
  if (params.restoreVersion) {
    return String(params.restoreVersion);
  }
  return undefined;
}

function legacyAlwaysApplyResponse(): boolean {
  return true;
}

async function loadSelectionFns(): Promise<DatasetVersionSelectionFns> {
  try {
    const loaded = await import('../src/app/mlops/hooks/task/forms/datasetVersionSelection.ts');
    if (
      typeof loaded.resolveDatasetVersionRestore === 'function' &&
      typeof loaded.shouldApplyDatasetVersionResponse === 'function'
    ) {
      return {
        resolveDatasetVersionRestore: loaded.resolveDatasetVersionRestore,
        shouldApplyDatasetVersionResponse: loaded.shouldApplyDatasetVersionResponse,
      };
    }
  } catch {
    // RED：选择逻辑尚未抽出，回退到当前无条件回填行为。
  }

  return {
    resolveDatasetVersionRestore: legacyUnconditionalRestore,
    shouldApplyDatasetVersionResponse: legacyAlwaysApplyResponse,
  };
}

function testSwitchDatasetDoesNotRestoreOldVersion(fns: DatasetVersionSelectionFns) {
  const restored = fns.resolveDatasetVersionRestore({
    restoreVersion: datasetAVersion,
    options: datasetBOptions,
    allowRestore: false,
  });

  assert.equal(
    restored,
    undefined,
    `切换数据集后不得回填旧 dataset_version，实际回填了 ${String(restored)}`,
  );
}

function testEditRestoresVersionInCurrentOptions(fns: DatasetVersionSelectionFns) {
  const restored = fns.resolveDatasetVersionRestore({
    restoreVersion: datasetAVersion,
    options: datasetAOptions,
    allowRestore: true,
  });

  assert.equal(restored, datasetAVersion, '首次编辑应回填属于当前 options 的原版本');
}

function testEditDoesNotRestoreVersionOutsideOptions(fns: DatasetVersionSelectionFns) {
  const restored = fns.resolveDatasetVersionRestore({
    restoreVersion: datasetAVersion,
    options: datasetBOptions,
    allowRestore: true,
  });

  assert.equal(
    restored,
    undefined,
    `原版本不属于当前 options 时不得回填，实际回填了 ${String(restored)}`,
  );
}

function testStaleGenerationIsIgnored(fns: DatasetVersionSelectionFns) {
  const applyStale = fns.shouldApplyDatasetVersionResponse({
    requestGeneration: 1,
    currentGeneration: 2,
    requestedDataset: 1,
    currentDataset: 2,
  });
  assert.equal(applyStale, false, '过期世代或数据集不匹配的版本响应必须忽略');

  const applyCurrent = fns.shouldApplyDatasetVersionResponse({
    requestGeneration: 2,
    currentGeneration: 2,
    requestedDataset: 2,
    currentDataset: 2,
  });
  assert.equal(applyCurrent, true, '当前世代且数据集匹配时才更新选项');
}

function testFormClearsVersionOnDatasetSwitch() {
  const formSource = readFileSync(formPath, 'utf8');

  assert.match(
    formSource,
    /from\s+['"]\.\/datasetVersionSelection['"]/,
    'useGenericDatasetForm 必须使用抽出的 datasetVersionSelection',
  );
  assert.doesNotMatch(
    formSource,
    /if\s*\(\s*formData\?\.dataset_version\s*\)[\s\S]{0,120}setFieldsValue\(\s*\{\s*dataset_version:\s*String\(\s*formData\.dataset_version\s*\)/,
    'renderOptions 不得再无条件回填 formData.dataset_version',
  );
  assert.match(
    formSource,
    /setFieldsValue\(\s*\{\s*dataset_version:\s*(?:undefined|null|['"]{2})\s*\}\s*\)/,
    '用户切换数据集时必须立即清空版本值',
  );
  assert.match(
    formSource,
    /setDatasetVersions\(\s*\[\s*\]\s*\)/,
    '用户切换数据集时必须立即清空旧 options',
  );
  assert.match(
    formSource,
    /shouldApplyDatasetVersionResponse|requestGeneration|currentGeneration/,
    '加载版本必须有请求世代保护',
  );
  assert.match(
    formSource,
    /datasetVersions\.some\(|options\.some\(/,
    '提交前必须校验版本属于已加载 options',
  );
}

function testModalDisablesConfirmWhileSelectLoading() {
  const modalSource = readFileSync(modalPath, 'utf8');
  assert.match(
    modalSource,
    /disabled=\{[^}]*loadingState\.select/,
    'TrainTaskModal 必须在 select loading 时禁用确认',
  );
}

async function main() {
  const fns = await loadSelectionFns();
  testSwitchDatasetDoesNotRestoreOldVersion(fns);
  testEditRestoresVersionInCurrentOptions(fns);
  testEditDoesNotRestoreVersionOutsideOptions(fns);
  testStaleGenerationIsIgnored(fns);
  testFormClearsVersionOnDatasetSwitch();
  testModalDisablesConfirmWhileSelectLoading();
  console.log('mlops-train-task-dataset-version-test: ok');
}

void main();
