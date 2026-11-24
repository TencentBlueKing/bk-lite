import '@ant-design/v5-patch-for-react-19';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import ImportModal from '../importModal';

const importPrecheck = vi.fn();
const importSubmit = vi.fn();

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'opsAnalysisSidebar.actionReuseTarget': '复用目标配置',
      'opsAnalysisSidebar.actionImportAsNew': '作为新数据源导入',
      'opsAnalysisSidebar.conflictReasonLabel.identity_config_conflict': '同一数据源配置不同',
      'opsAnalysisSidebar.startImport': '开始导入',
      'opsAnalysisSidebar.objectTypeDatasource': '数据源',
    }[key] || key),
  }),
}));

vi.mock('../../../api/importExport', () => ({
  useImportExportApi: () => ({ importPrecheck, importSubmit }),
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

describe('import conflict choices', () => {
  beforeEach(() => {
    importPrecheck.mockReset();
    importSubmit.mockReset();
    importPrecheck.mockResolvedValue({
      valid: true,
      conflicts: [
        {
          object_key: 'portable::window-identity',
          object_type: 'datasource',
          object_name: '时间窗口',
          reason: 'identity_config_conflict',
          suggested_actions: ['reuse_target', 'import_as_new'],
        },
      ],
      warnings: [],
      errors: [],
      counts: { total: 1, by_type: { datasource: 1 } },
    });
    importSubmit.mockResolvedValue({ success: true, results: [], summary: {} });
  });

  it('lets the importer choose reuse or a new copy and submits that choice', async () => {
    render(
      <ImportModal
        visible
        targetDirectoryId={null}
        onCancel={() => undefined}
      />,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['meta:\n  schema_version: "1.3.0"\n'], 'canvas.yaml', { type: 'text/yaml' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText('复用目标配置')).toBeTruthy();
    expect(screen.getByText('作为新数据源导入')).toBeTruthy();
    expect(screen.getByText('同一数据源配置不同')).toBeTruthy();
    const reuse = screen.getByRole('radio', { name: '复用目标配置' }) as HTMLInputElement;
    const asNew = screen.getByRole('radio', { name: '作为新数据源导入' }) as HTMLInputElement;
    expect(reuse.checked).toBe(true);
    expect(asNew.checked).toBe(false);

    fireEvent.click(asNew);
    fireEvent.click(screen.getByRole('button', { name: '开始导入' }));

    await waitFor(() => {
      expect(importSubmit).toHaveBeenCalledWith(expect.objectContaining({
        conflict_decisions: [
          { object_key: 'portable::window-identity', action: 'import_as_new' },
        ],
      }));
    });
  });
});
