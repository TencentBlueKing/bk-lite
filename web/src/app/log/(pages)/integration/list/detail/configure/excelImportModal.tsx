'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo
} from 'react';
import { Button, message, Upload } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import type { UploadProps } from 'antd';
import { CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import { excelCellToText } from '@/utils/excelCellText';
import {
  EXCEL_TEMPLATE_DATA_END_ROW,
  addExcelOptionSheet,
  applyExcelListValidation,
  applyExcelRangeValidation,
  excelColumnLetter,
} from '@/utils/excelListDataValidation';
import ExcelJS from 'exceljs';

interface ExcelImportModalProps {
  onSuccess: (data: any[]) => void;
}

interface ColumnConfig {
  name: string;
  label: string;
  type: 'select' | 'input' | 'group_select' | 'inputNumber';
  required?: boolean;
  widget_props?: {
    mode?: 'multiple';
    placeholder?: string;
    options?: { label: string; value: any }[];
    min?: number;
    max?: number;
  };
  default_value?: any;
}

interface ModalConfig {
  title: string;
  columns: ColumnConfig[];
  nodeList?: any[];
  pluginName?: string;
}

export interface ExcelImportModalRef {
  showModal: (config: ModalConfig) => void;
}

const ExcelImportModal = forwardRef<ExcelImportModalRef, ExcelImportModalProps>(
  ({ onSuccess }, ref) => {
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [fileList, setFileList] = useState<any[]>([]);
    const [parsedData, setParsedData] = useState<any[]>([]);
    const [columns, setColumns] = useState<ColumnConfig[]>([]);
    const [nodeList, setNodeList] = useState<any[]>([]);
    const [pluginName, setPluginName] = useState<string>('');
    const { t } = useTranslation();
    const { Dragger } = Upload;
    const userContext = useUserInfoContext();

    // Get group list from userContext
    const groupList = useMemo(() => {
      if (!userContext?.groupTree) return [];
      const treeSelectData = convertGroupTreeToTreeSelectData(
        userContext.groupTree
      );
      // Recursively extract all group nodes with full path
      const flattenTree = (nodes: any[], parentPath = ''): any[] => {
        return nodes.reduce((acc, node) => {
          const currentPath = parentPath
            ? `${parentPath}/${node.title}`
            : node.title;
          acc.push({
            label: currentPath,
            value: node.value,
            name: node.title,
            originalLabel: node.title
          });
          if (node.children && node.children.length > 0) {
            acc.push(...flattenTree(node.children, currentPath));
          }
          return acc;
        }, [] as any[]);
      };
      return flattenTree(treeSelectData);
    }, [userContext?.groupTree]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, columns, nodeList = [], pluginName = '' }) => {
        setVisible(true);
        setTitle(title);
        setFileList([]);
        setParsedData([]);
        setColumns(columns);
        setNodeList(nodeList);
        setPluginName(pluginName);
      }
    }));

    const handleSubmit = () => {
      if (!parsedData || parsedData.length === 0) {
        message.error(t('monitor.integrations.noImportData'));
        return;
      }
      // Validate required fields
      const fieldValidationResult = validateFields(parsedData);
      if (!fieldValidationResult.isValid) {
        message.error(
          fieldValidationResult.errorMsg || t('common.fieldRequired')
        );
        return;
      }
      setConfirmLoading(true);
      try {
        onSuccess(parsedData);
        const successMsg = t('monitor.integrations.importSuccessCount', '', {
          count: parsedData.length
        });
        message.success(successMsg);
        handleCancel();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleChange: UploadProps['onChange'] = ({ fileList }) => {
      setFileList(fileList);
    };

    const customRequest = async (options: any) => {
      const { file, onSuccess: onHandleSuccess, onError } = options;
      // Validate file size (20MB)
      const maxSize = 20 * 1024 * 1024;
      if (file.size > maxSize) {
        message.error(t('monitor.integrations.fileSizeExceeded'));
        onError(new Error('File size exceeded'));
        return;
      }
      // Parse Excel file using exceljs
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const buffer = e.target?.result as ArrayBuffer;
          const workbook = new ExcelJS.Workbook();
          await workbook.xlsx.load(buffer);
          const firstSheet = workbook.worksheets[0];
          if (!firstSheet || firstSheet.rowCount < 2) {
            message.error(t('monitor.integrations.emptyExcelFile'));
            onError(new Error('Empty file'));
            return;
          }
          // Parse headers and data. Hyperlink/rich-text cells must use excelCellToText.
          const headers: string[] = [];
          firstSheet.getRow(1).eachCell((cell) => {
            headers.push(excelCellToText(cell.value));
          });
          const rows: any[][] = [];
          for (let i = 2; i <= firstSheet.rowCount; i++) {
            const row: any[] = [];
            firstSheet
              .getRow(i)
              .eachCell({ includeEmpty: true }, (cell, colNumber) => {
                row[colNumber - 1] = excelCellToText(cell.value);
              });
            rows.push(row);
          }
          // Convert data to object array
          const parsedRows = rows
            .filter((row) => row.some((cell) => excelCellToText(cell)))
            .map((row) => {
              const rowData: any = {};
              headers.forEach((header, index) => {
                // Remove suffix hints from header, e.g., "(supports multiple, separated by comma)"
                const cleanHeader = header
                  .replace(/\s*\([^)]*\)\s*$/, '')
                  .trim();
                const column = columns.find((col) => col.label === cleanHeader);
                if (column) {
                  const cellValue = row[index];
                  rowData[column.name] = transformCellValue(cellValue, column);
                }
              });
              return rowData;
            });
          setParsedData(parsedRows);
          onHandleSuccess('Ok');
        } catch (error) {
          message.error(t('monitor.integrations.parseExcelFailed'));
          onError(error);
        }
      };
      reader.readAsArrayBuffer(file);
    };

    // Validate required fields
    const validateFields = (
      data: any[]
    ): { isValid: boolean; errorMsg?: string } => {
      for (let rowIndex = 0; rowIndex < data.length; rowIndex++) {
        const row = data[rowIndex];
        for (const column of columns) {
          const { name, label, required = false } = column;
          const value = row[name];
          // Required validation
          if (required) {
            if (
              value === undefined ||
              value === null ||
              value === '' ||
              (Array.isArray(value) && value.length === 0)
            ) {
              return {
                isValid: false,
                errorMsg: `${t('common.row')} ${rowIndex + 1}: ${label} ${t(
                  'common.required'
                )}`
              };
            }
          }
        }
      }
      return { isValid: true };
    };

    // Transform cell value based on column type. Never toString() hyperlink/rich-text objects.
    const transformCellValue = (value: any, column: ColumnConfig) => {
      const text = excelCellToText(value);
      if (!text) {
        return column.default_value;
      }
      const isMultiple = column.widget_props?.mode === 'multiple';
      // Convert value based on column type
      switch (column.type) {
        case 'select':
          if (column.name === 'node_ids') {
            // Node selection: single select
            const node = nodeList.find((n) => n.label === text);
            return node ? node.value : null;
          }
          // Other select types based on mode
          if (isMultiple) {
            return text.split(',').map((v: string) => v.trim());
          }
          return text;
        case 'group_select':
          // Group selection: supports multiple, format "parent/child, parent/child2"
          if (column.name === 'group_ids') {
            const groupNames = text.split(',').map((g: string) => g.trim());
            // Match IDs from groupList based on full path
            const groupIds = groupList
              .filter((group) => {
                const fullPath = group.label || group.name;
                return groupNames.includes(fullPath);
              })
              .map((group) => group.value);
            return groupIds.length > 0 ? groupIds : [];
          }
          return text;
        case 'inputNumber':
          return Number(text);
        default:
          return text;
      }
    };

    const handleDownloadTemplate = async () => {
      // Create workbook using exceljs
      const workbook = new ExcelJS.Workbook();
      // Create main worksheet
      const mainSheet = workbook.addWorksheet(
        t('monitor.integrations.dataTemplate')
      );
      // Set headers (add multiple selection hint)
      const headers = columns.map((col) => {
        const isMultiple =
          col.widget_props?.mode === 'multiple' || col.type === 'group_select';
        return isMultiple
          ? `${col.label} (${t('monitor.integrations.multipleSupport')})`
          : col.label;
      });
      mainSheet.addRow(headers);
      // Set header styles
      mainSheet.getRow(1).font = { bold: true };
      mainSheet.getRow(1).fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FFE0E0E0' }
      };
      // Store column validation info
      const columnValidations: Map<
        number,
        { sheetName: string; options: string[] }
      > = new Map();
      // Process data validation for each column with options
      columns.forEach((col, index) => {
        let optionsList: string[] = [];
        let sheetName = '';
        // Set column width
        mainSheet.getColumn(index + 1).width = 25;
        if (col.type === 'select' && col.name === 'node_ids') {
          // Node column
          if (nodeList && nodeList.length > 0) {
            optionsList = nodeList.map((node) => node.label);
            sheetName = `${col.label}${t(
              'monitor.integrations.optionsSuffix'
            )}`;
          }
        } else if (col.type === 'group_select') {
          // Group column, use full path (parent/child)
          if (groupList && groupList.length > 0) {
            optionsList = groupList.map(
              (group: any) => group.label || group.name
            );
            sheetName = `${col.label}${t(
              'monitor.integrations.optionsSuffix'
            )}`;
          }
        } else if (col.widget_props?.options) {
          // Other columns with options
          optionsList = col.widget_props.options.map((opt: any) => opt.label);
          sheetName = `${col.label}${t('monitor.integrations.optionsSuffix')}`;
        }
        // Node/org options live on independent sheets; main sheet uses list DV.
        if (optionsList.length > 0 && sheetName) {
          const finalSheetName = addExcelOptionSheet(
            workbook,
            sheetName,
            optionsList
          );
          columnValidations.set(index, {
            sheetName: finalSheetName,
            options: optionsList
          });
        }
      });
      // One range validation per column — no per-cell custom DV on rows 2–1001
      columns.forEach((column, colIndex) => {
        const columnLetter = excelColumnLetter(colIndex);
        const validation = columnValidations.get(colIndex);
        const range = `${columnLetter}2:${columnLetter}${EXCEL_TEMPLATE_DATA_END_ROW}`;
        if (validation) {
          const isMultiple =
            column.widget_props?.mode === 'multiple' ||
            column.type === 'group_select';
          applyExcelListValidation(
            mainSheet,
            colIndex,
            validation.sheetName,
            validation.options.length,
            {
              allowBlank: !column.required,
              showErrorMessage: !isMultiple,
              errorTitle: t('monitor.integrations.inputError'),
              error: t('monitor.integrations.selectFromDropdown'),
              promptTitle: column.label,
              showInputMessage: true
            }
          );
          return;
        }
        if (column.required && column.type !== 'inputNumber') {
          applyExcelRangeValidation(mainSheet, range, {
            type: 'textLength',
            operator: 'greaterThan',
            allowBlank: false,
            formulae: [0],
            showErrorMessage: true,
            errorTitle: t('monitor.integrations.inputError'),
            error: t('common.required'),
            promptTitle: column.label,
            showInputMessage: true
          });
          return;
        }
        if (column.type === 'inputNumber') {
          const min = column.widget_props?.min ?? 0;
          const max = column.widget_props?.max ?? 999999999;
          applyExcelRangeValidation(mainSheet, range, {
            type: 'whole',
            operator: 'between',
            allowBlank: !column.required,
            formulae: [min, max],
            showErrorMessage: true,
            errorTitle: t('monitor.integrations.inputError'),
            error: t('monitor.integrations.numberRangeError', '', {
              min,
              max
            }),
            promptTitle: column.label,
            showInputMessage: true,
            prompt: t('monitor.integrations.numberRangeError', '', {
              min,
              max
            })
          });
        }
      });
      // Generate file and download
      const buffer = await workbook.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const fileName = pluginName
        ? `${pluginName}_${t('monitor.integrations.importTemplate')}.xlsx`
        : `${t('monitor.integrations.importTemplate')}.xlsx`;
      link.download = fileName;
      link.click();
      window.URL.revokeObjectURL(url);
    };

    const handleCancel = () => {
      setVisible(false);
      setParsedData([]);
      setFileList([]);
    };

    const beforeUpload = (file: File) => {
      const isXlsx =
        file.type ===
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
        file.name.endsWith('.xlsx');
      if (!isXlsx) {
        message.error(t('monitor.integrations.onlyXlsxAllowed'));
      }
      const maxSize = 20 * 1024 * 1024;
      if (file.size > maxSize) {
        message.error(t('monitor.integrations.fileSizeExceeded'));
      }
      return isXlsx && file.size <= maxSize;
    };

    return (
      <OperateModal
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              disabled={!parsedData || parsedData.length === 0}
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Dragger
          customRequest={customRequest}
          onChange={handleChange}
          fileList={fileList}
          accept=".xlsx"
          maxCount={1}
          beforeUpload={beforeUpload}
          className="w-full"
        >
          <p className="ant-upload-drag-icon">
            <CloudUploadOutlined />
          </p>
          <p className="flex justify-center content-center items-center">
            {t('common.uploadText')}
            <Button type="link">{t('monitor.integrations.clickUpload')}</Button>
          </p>
        </Dragger>
        <div className="mt-[16px]">
          <p className="text-[12px] text-[var(--color-text-3)]">
            {t('monitor.integrations.excelImportTips')}
          </p>
          <Button
            className="p-0"
            icon={<DownloadOutlined />}
            onClick={handleDownloadTemplate}
            type="link"
          >
            {t('monitor.integrations.downloadTemplate')}
          </Button>
        </div>
      </OperateModal>
    );
  }
);

ExcelImportModal.displayName = 'ExcelImportModal';
export default ExcelImportModal;
