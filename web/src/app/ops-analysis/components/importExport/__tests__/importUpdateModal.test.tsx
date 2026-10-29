import '@ant-design/v5-patch-for-react-19';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ImportUpdateModal from '../importUpdateModal';

const importUpdateCanvas = vi.fn();

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

vi.mock('../../../api/importExport', () => ({
  useImportExportApi: () => ({ importUpdateCanvas }),
}));

describe('import update modal', () => {
  beforeEach(() => {
    importUpdateCanvas.mockReset();
    importUpdateCanvas.mockResolvedValue({
      canvas_id: 9,
      name: 'renamed',
      desc: 'from-yaml',
    });
  });

  it('asks to overwrite the current canvas and submits the uploaded yaml for that id', async () => {
    const onSuccess = vi.fn();
    render(
      <ImportUpdateModal
        visible
        objectType="topology"
        objectId={9}
        objectName="当前拓扑"
        onCancel={() => undefined}
        onSuccess={onSuccess}
      />,
    );

    expect(screen.getByText('opsAnalysisSidebar.importUpdateOverwrite')).toBeTruthy();
    expect(screen.getByText('当前拓扑')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'common.confirm' }) as HTMLButtonElement).disabled).toBe(true);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['meta:\n  schema_version: "1.2.0"\n'], 'canvas.yaml', {
      type: 'text/yaml',
    });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect((screen.getByRole('button', { name: 'common.confirm' }) as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));

    await waitFor(() => {
      expect(importUpdateCanvas).toHaveBeenCalledWith({
        object_type: 'topology',
        object_id: 9,
        yaml_content: 'meta:\n  schema_version: "1.2.0"\n',
      });
    });
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith({
        canvas_id: 9,
        name: 'renamed',
        desc: 'from-yaml',
      });
    });
  });

  it('asks again on each confirm and does not submit when the user cancels', async () => {
    const beforeSubmit = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(
      <ImportUpdateModal
        visible
        objectType="dashboard"
        objectId={3}
        objectName="当前仪表盘"
        onCancel={() => undefined}
        beforeSubmit={beforeSubmit}
      />,
    );

    expect(beforeSubmit).not.toHaveBeenCalled();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(['name: renamed\n'], 'canvas.yaml', { type: 'text/yaml' })],
      },
    });
    const confirm = () => screen.getByRole('button', { name: 'common.confirm' });
    await waitFor(() => {
      expect((confirm() as HTMLButtonElement).disabled).toBe(false);
    });

    fireEvent.click(confirm());
    await waitFor(() => {
      expect(beforeSubmit).toHaveBeenCalledTimes(1);
    });
    expect(importUpdateCanvas).not.toHaveBeenCalled();

    fireEvent.click(confirm());
    await waitFor(() => {
      expect(beforeSubmit).toHaveBeenCalledTimes(2);
      expect(importUpdateCanvas).toHaveBeenCalledTimes(1);
    });
  });
});
