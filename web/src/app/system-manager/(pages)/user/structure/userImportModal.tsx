'use client';

import React, { forwardRef, useImperativeHandle, useMemo, useState } from 'react';
import { Button, Form, Upload, message } from 'antd';
import { CloseCircleFilled, CloudUploadOutlined, CopyOutlined, DownloadOutlined, ExclamationCircleFilled } from '@ant-design/icons';
import ExcelJS from 'exceljs';
import OperateModal from '@/components/operate-modal';
import { useUserApi } from '@/app/system-manager/api/user';
import { LOCALE_OPTIONS, ZONEINFO_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import type { UserImportFailure, UserImportResult } from '@/app/system-manager/types/user';
import { excelCellToText } from '@/app/system-manager/utils/excelCellText';
import { toGroupTreeSelectNodes, type ExtendedTreeDataNode } from '@/app/system-manager/utils/userTreeUtils';

interface UserImportModalProps {
  treeData: ExtendedTreeDataNode[];
  onSuccess: () => void;
}

export interface UserImportModalRef {
  showModal: () => void;
}

type ImportView = 'form' | 'result';

interface ImportRow {
  row_number: number;
  username?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  timezone?: string;
  locale?: string;
}

const REQUIRED_HEADERS = ['用户名', '姓名', '邮箱', '手机号'];
const HEADERS = [...REQUIRED_HEADERS, '时区（可选）', '语言（可选）'];
const FIELD_MAP: Record<string, string> = {
  用户名: 'username',
  姓名: 'lastName',
  邮箱: 'email',
  手机号: 'phone',
  '时区（可选）': 'timezone',
  '语言（可选）': 'locale',
};

const UserImportModal = forwardRef<UserImportModalRef, UserImportModalProps>(({ treeData, onSuccess }, ref) => {
  const groupTreeSelectData = useMemo(() => toGroupTreeSelectNodes(treeData), [treeData]);
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<ImportView>('form');
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [result, setResult] = useState<UserImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const { importUsers } = useUserApi();

  const failureGroups = useMemo(() => {
    return Object.values((result?.failures || []).reduce((groups: Record<string, { message: string; items: UserImportFailure[] }>, item: UserImportFailure) => {
      const failureMessage = item.message || t('system.user.import.unknownError');
      groups[failureMessage] = groups[failureMessage] || { message: failureMessage, items: [] };
      groups[failureMessage].items.push(item);
      return groups;
    }, {}));
  }, [result, t]);

  const resetFileState = () => {
    setRows([]);
    setFileName('');
    setResult(null);
    setView('form');
  };

  useImperativeHandle(ref, () => ({
    showModal: () => {
      form.resetFields();
      resetFileState();
      setOpen(true);
    },
  }), [form]);

  const downloadTemplate = async () => {
    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet('用户导入');
    const optionsSheet = workbook.addWorksheet('选项');
    optionsSheet.getColumn(1).values = ['平台支持的时区', ...ZONEINFO_OPTIONS.map((option) => option.value)];
    optionsSheet.getColumn(2).values = ['平台支持的语言', ...LOCALE_OPTIONS.map((option) => option.value)];
    optionsSheet.state = 'hidden';
    [1, 2, 3, 4].forEach((column) => {
      sheet.getColumn(column).numFmt = '@';
    });
    sheet.addRow(HEADERS);
    sheet.addRow(['zhangsan', '张三', '', '13800138000', '', '']);
    // 写成文本公式，避免 Excel 打开模板时把示例邮箱自动变成 mailto 超链接。
    sheet.getCell(2, 3).value = { formula: '"zhangsan@example.com"', result: 'zhangsan@example.com' };
    sheet.getCell(2, 3).numFmt = '@';
    const timezoneColumn = 5;
    const localeColumn = 6;
    for (let row = 2; row <= 501; row += 1) {
      sheet.getCell(row, 3).numFmt = '@';
      sheet.getCell(row, 4).numFmt = '@';
      sheet.getCell(row, timezoneColumn).dataValidation = {
        type: 'list', allowBlank: true, formulae: [`'选项'!$A$2:$A$${ZONEINFO_OPTIONS.length + 1}`],
      };
      sheet.getCell(row, localeColumn).dataValidation = {
        type: 'list', allowBlank: true, formulae: [`'选项'!$B$2:$B$${LOCALE_OPTIONS.length + 1}`],
      };
    }
    const buffer = await workbook.xlsx.writeBuffer();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    link.download = '用户导入模板.xlsx';
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const parseFile = async (file: File) => {
    try {
      if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error(t('system.user.import.xlsxOnly'));
      if (file.size > 20 * 1024 * 1024) throw new Error(t('system.user.import.fileTooLarge'));
      const workbook = new ExcelJS.Workbook();
      try {
        await workbook.xlsx.load(await file.arrayBuffer());
      } catch {
        throw new Error(t('system.user.import.parseFailed'));
      }
      const sheet = workbook.worksheets[0];
      const headers: string[] = [];
      sheet?.getRow(1).eachCell((cell) => headers.push(excelCellToText(cell.value)));
      if (!sheet || REQUIRED_HEADERS.some((header) => !headers.includes(header))) {
        throw new Error(t('system.user.import.invalidHeaders'));
      }
      const parsed: ImportRow[] = [];
      for (let index = 2; index <= sheet.rowCount; index += 1) {
        const values = sheet.getRow(index).values as unknown[];
        if (!values.slice(1).some((value) => excelCellToText(value))) continue;
        const row: ImportRow = { row_number: index };
        headers.forEach((header, column) => {
          const field = FIELD_MAP[header] as keyof Omit<ImportRow, 'row_number'> | undefined;
          if (field) row[field] = excelCellToText(values[column + 1]);
        });
        parsed.push(row);
      }
      if (!parsed.length) throw new Error(t('system.user.import.emptyFile'));
      if (parsed.length > 500) throw new Error(t('system.user.import.tooManyRows'));
      setRows(parsed);
      setFileName(file.name);
      setResult(null);
      message.success(t('system.user.import.readSuccess', '', { count: parsed.length }));
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : t('system.user.import.parseError'));
    }
    return false;
  };

  const submit = async () => {
    try {
      const { group_id } = await form.validateFields();
      if (!rows.length) {
        message.error(t('system.user.import.needFile'));
        return;
      }
      setLoading(true);
      const data = await importUsers({ group_id, file_name: fileName, users: rows });
      if (data.failed_count === 0) {
        message.success(t('system.user.import.allSuccess', '', { count: data.success_count }));
        setOpen(false);
        onSuccess();
        return;
      }
      setResult(data);
      setView('result');
      if (data.success_count) onSuccess();
    } catch {
      message.error(t('system.user.import.submitFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleChangeFile = () => {
    setRows([]);
    setFileName('');
    setResult(null);
    setView('form');
  };

  const copyFailures = async () => {
    const lines = failureGroups.flatMap((group) => group.items.map((item) => (
      t('system.user.import.failureRow', '', {
        row: item.row_number,
        username: item.username || t('system.user.import.emptyUsername'),
        message: group.message,
      })
    )));
    if (!lines.length) {
      message.warning(t('system.user.import.noFailureDetails'));
      return;
    }
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      message.success(t('system.user.import.copySuccess', '', { count: lines.length }));
    } catch {
      message.error(t('system.user.import.copyFailed'));
    }
  };

  const isResult = view === 'result';
  const noneImported = Boolean(result && result.success_count === 0);
  const hasFailureDetails = failureGroups.some((group) => group.items.length > 0);

  return (
    <OperateModal
      title={isResult ? t('system.user.import.resultTitle') : t('system.user.import.title')}
      open={open}
      onCancel={handleClose}
      onOk={isResult ? undefined : submit}
      okText={t('common.import')}
      cancelText={t('common.cancel')}
      okButtonProps={{ loading }}
      width={720}
      footer={isResult ? (
        <div className="flex justify-end gap-2">
          <Button onClick={handleChangeFile}>{t('system.user.import.changeFile')}</Button>
          <Button type="primary" autoFocus onClick={handleClose}>{t('common.close')}</Button>
        </div>
      ) : undefined}
    >
      {isResult && result ? (
        <div>
          <div className="sticky top-0 z-10 flex items-start justify-between gap-3 bg-[var(--color-bg)] pb-3">
            <div className="flex min-w-0 items-center gap-2" role="status">
              {noneImported ? (
                <CloseCircleFilled aria-hidden className="text-[16px] text-[var(--color-fail)]" />
              ) : (
                <ExclamationCircleFilled aria-hidden className="text-[16px] text-[var(--color-warning)]" />
              )}
              <div className="min-w-0">
                <div className="text-[14px] font-semibold leading-normal text-[var(--color-text-1)]">
                  {noneImported ? t('system.user.import.noneImported') : t('system.user.import.partialTitle')}
                </div>
                <div className="mt-1 min-w-0 break-all text-[12px] font-medium tabular-nums leading-normal text-[var(--color-text-3)]">
                  {noneImported
                    ? t('system.user.import.failedCountLabel', '', { count: result.failed_count })
                    : t('system.user.import.partialHint', '', {
                      successCount: result.success_count,
                      failedCount: result.failed_count,
                    })}
                  {fileName ? ` · ${fileName}` : ''}
                </div>
              </div>
            </div>
            {hasFailureDetails && (
              <Button type="link" size="small" icon={<CopyOutlined aria-hidden />} onClick={copyFailures} className="!h-auto shrink-0 !px-0">
                {t('system.user.import.copyFailures')}
              </Button>
            )}
          </div>
          {hasFailureDetails ? (
            <div className="divide-y divide-[var(--color-border)]">
              {failureGroups.map((group) => (
                <section key={group.message} className="py-4 first:pt-0 last:pb-0">
                  <h3 className="mb-2 mt-0 text-[14px] font-semibold leading-normal text-[var(--color-text-1)]">
                    {group.message}
                  </h3>
                  <ul className="m-0 list-none space-y-1 p-0">
                    {group.items.map((item, index) => (
                      <li
                        key={`${item.row_number}-${item.username || 'empty'}-${index}`}
                        className="flex items-start gap-3 text-[14px] leading-normal"
                      >
                        <span className="shrink-0 whitespace-nowrap tabular-nums text-[var(--color-text-3)]">
                          {t('system.user.import.failureRowNo', '', { row: item.row_number })}
                        </span>
                        <span className="min-w-0 break-all text-[var(--color-text-1)]" title={item.username || undefined}>
                          {item.username || t('system.user.import.emptyUsername')}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <div className="text-[14px] leading-normal text-[var(--color-text-3)]">
              {t('system.user.import.noFailureDetails')}
            </div>
          )}
        </div>
      ) : (
        <>
          <Form form={form} layout="vertical">
            <Form.Item
              name="group_id"
              label={t('system.user.import.targetGroup')}
              rules={[{ required: true, message: t('system.user.import.targetGroupRequired') }]}
            >
              <GroupTreeSelect
                multiple={false}
                showSearch
                allowClear
                treeData={groupTreeSelectData}
                placeholder={t('system.user.import.targetGroupRequired')}
              />
            </Form.Item>
          </Form>
          <div className="mt-3 mb-2 text-[12px] text-[var(--color-text-3)]">
            <div>{t('system.user.import.fileHint')}</div>
            <Button type="link" size="small" icon={<DownloadOutlined />} onClick={downloadTemplate} className="!h-auto !px-0">
              {t('system.user.import.downloadTemplate')}
            </Button>
          </div>
          <Upload.Dragger accept=".xlsx" maxCount={1} beforeUpload={parseFile} showUploadList={false}>
            <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
            <p>{t('system.user.import.uploadHint')}</p>
          </Upload.Dragger>
          {rows.length > 0 && (
            <div className="mt-3 text-[14px] text-[var(--color-text-2)]">
              {t('system.user.import.fileRead', '', { fileName, count: rows.length })}
            </div>
          )}
        </>
      )}
    </OperateModal>
  );
});

UserImportModal.displayName = 'UserImportModal';
export default UserImportModal;
