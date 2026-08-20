import ExcelJS from 'exceljs';

import type {
  BaselineComplianceHostDetail,
  BaselineCompliancePatchDetail,
  BaselineCompliancePerspective,
} from '@/app/patch-manager/types';
import { formatComplianceEvidence } from './presentation';

type ComplianceDetail = BaselineComplianceHostDetail | BaselineCompliancePatchDetail;
type Translate = (key: string) => string;

interface BuildComplianceWorkbookOptions {
  perspective: BaselineCompliancePerspective;
  rows: ComplianceDetail[];
  translate: Translate;
  formatTime: (value?: string | null) => string;
}

export function buildBaselineComplianceWorkbook({
  perspective,
  rows,
  translate,
  formatTime,
}: BuildComplianceWorkbookOptions): ExcelJS.Workbook {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet(translate(
    perspective === 'host'
      ? 'patchManager.baseline.complianceDetail.hostPerspective'
      : 'patchManager.baseline.complianceDetail.patchPerspective',
  ));

  if (perspective === 'host') {
    sheet.columns = [
      { header: translate('patchManager.baseline.complianceDetail.patch'), key: 'identifier', width: 20 },
      { header: translate('patchManager.baseline.description'), key: 'title', width: 34 },
      { header: translate('patchManager.severity'), key: 'severity', width: 14 },
      { header: translate('patchManager.baseline.complianceDetail.requirement'), key: 'condition', width: 34 },
      { header: translate('patchManager.baseline.complianceDetail.assessmentStatus'), key: 'status', width: 16 },
      { header: translate('patchManager.baseline.complianceDetail.evidence'), key: 'evidence', width: 42 },
      { header: translate('patchManager.baseline.complianceDetail.reason'), key: 'reason', width: 34 },
      { header: translate('patchManager.baseline.complianceDetail.assessedAt'), key: 'evaluatedAt', width: 22 },
    ];
    rows.forEach((item) => {
      const row = item as BaselineComplianceHostDetail;
      sheet.addRow({
        identifier: row.identifier,
        title: row.title,
        severity: row.severity_display || row.severity,
        condition: row.condition,
        status: translate(`patchManager.baseline.complianceDetail.status.${row.status}`),
        evidence: formatComplianceEvidence(row.evidence),
        reason: row.reason || '--',
        evaluatedAt: formatTime(row.evaluated_at) || '--',
      });
    });
  } else {
    sheet.columns = [
      { header: translate('patchManager.baseline.complianceDetail.host'), key: 'host', width: 24 },
      { header: 'IP', key: 'ip', width: 18 },
      { header: translate('patchManager.baseline.complianceDetail.assessmentStatus'), key: 'status', width: 16 },
      { header: translate('patchManager.baseline.complianceDetail.evidence'), key: 'evidence', width: 42 },
      { header: translate('patchManager.baseline.complianceDetail.reason'), key: 'reason', width: 34 },
      { header: translate('patchManager.baseline.complianceDetail.assessedAt'), key: 'evaluatedAt', width: 22 },
    ];
    rows.forEach((item) => {
      const row = item as BaselineCompliancePatchDetail;
      sheet.addRow({
        host: row.target_name,
        ip: row.target_ip,
        status: translate(`patchManager.baseline.complianceDetail.status.${row.status}`),
        evidence: formatComplianceEvidence(row.evidence),
        reason: row.reason || '--',
        evaluatedAt: formatTime(row.evaluated_at) || '--',
      });
    });
  }

  sheet.views = [{ state: 'frozen', ySplit: 1 }];
  sheet.getRow(1).font = { bold: true };
  sheet.eachRow((row, rowNumber) => {
    if (rowNumber === 1) return;
    row.alignment = { vertical: 'top', wrapText: true };
  });
  return workbook;
}

export async function downloadBaselineComplianceWorkbook(
  workbook: ExcelJS.Workbook,
  filename: string,
): Promise<void> {
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function sanitizeExportFilename(value: string): string {
  return value.replace(/[\\/:*?"<>|]/g, '-');
}
