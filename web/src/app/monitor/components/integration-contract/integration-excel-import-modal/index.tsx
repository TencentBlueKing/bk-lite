'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
} from 'react';
import { Button, message } from 'antd';
import ImportFileModalShell from '@/components/import-file-modal-shell';
import { useTranslation } from '@/utils/i18n';
import type { UploadProps } from 'antd';
import { CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import ExcelJS from 'exceljs';

interface ColumnRule {
  type?: string;
  pattern?: string;
  message?: string;
  excel_formula?: string;
}

interface ColumnOption {
  label: string;
  value: unknown;
}

export interface IntegrationExcelImportColumnConfig {
  name: string;
  label: string;
  excel_label?: string;
  type: 'select' | 'input' | 'group_select' | 'inputNumber' | 'auth_input';
  required?: boolean;
  widget_props?: {
    mode?: 'multiple';
    placeholder?: string;
    options?: ColumnOption[];
    min?: number;
    max?: number;
  };
  default_value?: unknown;
  rules?: ColumnRule[];
  is_only?: boolean;
}

interface ModalConfig {
  title: string;
  columns: IntegrationExcelImportColumnConfig[];
  nodeList?: { label: string; value: unknown }[];
  groupList?: { label: string; value: unknown }[];
  pluginName?: string;
}

export interface IntegrationExcelImportModalRef {
  showModal: (config: ModalConfig) => void;
}

interface IntegrationExcelImportModalProps {
  onSuccess: (data: Record<string, unknown>[]) => void;
}

const IntegrationExcelImportModal = forwardRef<
  IntegrationExcelImportModalRef,
  IntegrationExcelImportModalProps
>(({ onSuccess }, ref) => {
  const [open, setOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [title, setTitle] = useState('');
  const [fileList, setFileList] = useState<unknown[]>([]);
  const [parsedData, setParsedData] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<IntegrationExcelImportColumnConfig[]>([]);
  const [nodeList, setNodeList] = useState<{ label: string; value: unknown }[]>([]);
  const [groupListProp, setGroupListProp] = useState<{ label: string; value: unknown }[]>([]);
  const [pluginName, setPluginName] = useState('');
  const { t } = useTranslation();
  const userContext = useUserInfoContext();

  const defaultGroupList = useMemo(() => {
    if (!userContext?.groupTree) return [];
    const treeSelectData = convertGroupTreeToTreeSelectData(userContext.groupTree);
    const flattenTree = (nodes: any[], parentPath = ''): any[] => {
      return nodes.reduce((acc, node) => {
        const currentPath = parentPath ? `${parentPath}/${node.title}` : node.title;
        acc.push({
          label: currentPath,
          value: node.value,
          name: node.title,
          originalLabel: node.title,
        });
        if (node.children && node.children.length > 0) {
          acc.push(...flattenTree(node.children, currentPath));
        }
        return acc;
      }, [] as any[]);
    };
    return flattenTree(treeSelectData);
  }, [userContext?.groupTree]);

  const groupList = groupListProp.length > 0 ? groupListProp : defaultGroupList;

  useImperativeHandle(ref, () => ({
    showModal: ({ title, columns, nodeList = [], groupList = [], pluginName = '' }) => {
      setOpen(true);
      setTitle(title);
      setFileList([]);
      setParsedData([]);
      setColumns(columns);
      setNodeList(nodeList);
      setGroupListProp(groupList);
      setPluginName(pluginName);
    },
  }));

  const handleSubmit = () => {
    if (!parsedData || parsedData.length === 0) {
      message.error(t('monitor.integrations.noImportData'));
      return;
    }

    const fieldValidationResult = validateFields(parsedData);
    if (!fieldValidationResult.isValid) {
      message.error(fieldValidationResult.errorMsg || t('common.fieldRequired'));
      return;
    }

    const uniqueCheckResult = validateUniqueness(parsedData);
    if (!uniqueCheckResult.isValid) {
      const errorMsg = t('monitor.integrations.duplicateFieldError')
        .replace('{{field}}', uniqueCheckResult.field || '')
        .replace('{{value}}', uniqueCheckResult.value || '');
      message.error(errorMsg);
      return;
    }

    setConfirmLoading(true);
    try {
      const normalizedData = parsedData.map((row) => {
        if (row.auth_type === 'private_key') {
          return {
            ...row,
            password: '',
            private_key: '',
            key_file_name: undefined,
          };
        }
        return row;
      });
      onSuccess(normalizedData);
      const successMsg = t('monitor.integrations.importSuccessCount').replace(
        '{{count}}',
        parsedData.length.toString(),
      );
      message.success(successMsg);
      handleCancel();
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleChange: UploadProps['onChange'] = ({ fileList }) => {
    setFileList(fileList as unknown[]);
  };

  const customRequest = async (options: any) => {
    const { file, onSuccess: onHandleSuccess, onError } = options;
    const maxSize = 20 * 1024 * 1024;
    if (file.size > maxSize) {
      message.error(t('monitor.integrations.fileSizeExceeded'));
      onError(new Error('File size exceeded'));
      return;
    }

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

        const headers: string[] = [];
        firstSheet.getRow(1).eachCell((cell) => {
          headers.push(cell.value?.toString() || '');
        });

        const rows: unknown[][] = [];
        for (let i = 2; i <= firstSheet.rowCount; i++) {
          const row: unknown[] = [];
          firstSheet
            .getRow(i)
            .eachCell({ includeEmpty: true }, (cell, colNumber) => {
              row[colNumber - 1] = cell.value;
            });
          rows.push(row);
        }

        const parsedRows = rows
          .filter((row) => row.some((cell) => cell !== null && cell !== ''))
          .map((row) => {
            const rowData: Record<string, unknown> = {};
            headers.forEach((header, index) => {
              const cleanHeader = header.replace(/\s*\([^)]*\)\s*$/, '').trim();
              const column = columns.find(
                (col) => (col.excel_label || col.label) === cleanHeader,
              );
              if (column) {
                rowData[column.name] = transformCellValue(row[index], column);
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

  const validateFields = (
    data: Record<string, unknown>[],
  ): { isValid: boolean; errorMsg?: string } => {
    for (let rowIndex = 0; rowIndex < data.length; rowIndex++) {
      const row = data[rowIndex];
      for (const column of columns) {
        const { name, label, required = false, rules = [] } = column;
        const value = row[name];
        if (
          required &&
          (value === undefined ||
            value === null ||
            value === '' ||
            (Array.isArray(value) && value.length === 0))
        ) {
          return {
            isValid: false,
            errorMsg: `${t('common.row')} ${rowIndex + 1}: ${label} ${t('common.required')}`,
          };
        }

        if (rules.length > 0) {
          for (const rule of rules) {
            if (rule.type === 'pattern' && value !== undefined && value !== null && value !== '') {
              const stringValue = String((value as any)?.text || value || '').trim();
              const regex = new RegExp(rule.pattern);
              if (!regex.test(stringValue)) {
                return {
                  isValid: false,
                  errorMsg: `${t('common.row')} ${rowIndex + 1}: ${label} ${
                    rule.message || t('common.required')
                  }`,
                };
              }
            }
          }
        }
      }
    }
    return { isValid: true };
  };

  const validateUniqueness = (
    data: Record<string, unknown>[],
  ): { isValid: boolean; field?: string; value?: string } => {
    const uniqueFields = columns.filter((col) => col.is_only === true);
    for (const field of uniqueFields) {
      const valueSet = new Set<string>();
      for (const row of data) {
        const value = row[field.name];
        if (value === null || value === undefined || value === '') continue;
        const valueStr = String(value);
        if (valueSet.has(valueStr)) {
          return {
            isValid: false,
            field: field.label,
            value: valueStr,
          };
        }
        valueSet.add(valueStr);
      }
    }
    return { isValid: true };
  };

  const transformCellValue = (
    value: unknown,
    column: IntegrationExcelImportColumnConfig,
  ) => {
    if (value === null || value === undefined || value === '') {
      return column.default_value;
    }

    const isMultiple = column.widget_props?.mode === 'multiple';

    switch (column.type) {
      case 'select':
        if (column.name === 'node_ids') {
          const nodeName = String(value).trim();
          const node = nodeList.find((item) => item.label === nodeName);
          return node ? node.value : null;
        }
        if (isMultiple) {
          return String(value)
            .split(',')
            .map((v) => v.trim());
        }
        return value;
      case 'group_select':
        if (column.name === 'group_ids') {
          const groupNames = String(value)
            .split(',')
            .map((g) => g.trim());
          const groupIds = groupList
            .filter((group: any) => {
              const fullPath = group.label || group.name;
              return groupNames.includes(fullPath);
            })
            .map((group: any) => group.value);
          return groupIds.length > 0 ? groupIds : [];
        }
        return value;
      case 'inputNumber':
        return Number(value);
      case 'auth_input':
        return String((value as any)?.text || value || '');
      default:
        return value;
    }
  };

  const generateTemplate = async () => {
    if (!columns.length) {
      message.error(t('monitor.integrations.noTemplateColumns'));
      return;
    }

    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Template');

    const headers = columns.map((col) => {
      const isMultiple = col.widget_props?.mode === 'multiple' || col.type === 'group_select';
      const baseLabel = col.excel_label || col.label;
      return isMultiple ? `${baseLabel} (${t('node-manager.cloudregion.integrations.multipleSelectHint')})` : baseLabel;
    });
    worksheet.addRow(headers);
    worksheet.getRow(1).font = { bold: true };
    worksheet.columns.forEach((column) => {
      column.width = 24;
    });

    const columnValidations = new Map<number, { sheetName: string; options: string[] }>();
    columns.forEach((col, index) => {
      let options: string[] = [];
      let sheetName = '';
      if (col.type === 'group_select') {
        options = groupList.map((group: any) => group.label);
        if (options.length > 0) {
          sheetName = `${col.label}_${t('node-manager.cloudregion.integrations.options')}`;
        }
      } else if (col.type === 'select' && col.widget_props?.options) {
        options = col.widget_props.options.map((opt) => opt.label);
        if (options.length > 0) {
          sheetName = `${col.label}_${t('node-manager.cloudregion.integrations.options')}`;
        }
      }

      if (options.length > 0 && sheetName) {
        const optionsSheet = workbook.addWorksheet(sheetName);
        options.forEach((opt) => optionsSheet.addRow([opt]));
        optionsSheet.getColumn(1).width = 30;
        optionsSheet.state = 'hidden';
        columnValidations.set(index + 1, { sheetName, options });
      }
    });

    const sampleRow = columns.map((col) => {
      if (col.default_value !== undefined) {
        return col.default_value;
      }
      if (col.type === 'group_select') {
        return groupList[0]?.label || '';
      }
      if (col.name === 'node_ids') {
        return nodeList[0]?.label || '';
      }
      return '';
    });
    worksheet.addRow(sampleRow);

    columns.forEach((column, colIndex) => {
      const columnLetter = String.fromCharCode(65 + colIndex);
      const validation = columnValidations.get(colIndex + 1);

      for (let row = 2; row <= 1001; row++) {
        const cell = worksheet.getCell(`${columnLetter}${row}`);

        if (
          column.required &&
          !validation &&
          column.type !== 'inputNumber' &&
          !column.rules?.length
        ) {
          cell.dataValidation = {
            type: 'textLength',
            operator: 'greaterThan',
            allowBlank: false,
            formulae: [0],
            showErrorMessage: true,
            errorTitle: t('node-manager.cloudregion.integrations.error'),
            error: t('common.required'),
            promptTitle: column.label,
            showInputMessage: true,
          };
          continue;
        }

        if (validation) {
          const isMultiple =
            column.widget_props?.mode === 'multiple' || column.type === 'group_select';
          if (!isMultiple) {
            cell.dataValidation = {
              type: 'list',
              allowBlank: !column.required,
              formulae: [`'${validation.sheetName}'!$A$1:$A$${validation.options.length}`],
              showErrorMessage: true,
              errorTitle: t('node-manager.cloudregion.integrations.error'),
              error: t('node-manager.cloudregion.integrations.pleaseSelectFromDropdown'),
              promptTitle: column.label,
              showInputMessage: true,
            };
          } else {
            const optionsList = validation.options.map((opt) => `"${opt}"`).join(',');
            let formula = '';
            if (column.required) {
              formula = `AND(LEN(${columnLetter}${row})>0,SUMPRODUCT(--ISNUMBER(MATCH(TRIM(MID(SUBSTITUTE(${columnLetter}${row},\",\",REPT(\" \",100)),ROW(INDIRECT(\"1:\"&LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},\",\",\"\"))+1))*100-99,100)),{${optionsList}},0)))=LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},\",\",\"\"))+1)`;
            } else {
              formula = `OR(LEN(${columnLetter}${row})=0,AND(LEN(${columnLetter}${row})>0,SUMPRODUCT(--ISNUMBER(MATCH(TRIM(MID(SUBSTITUTE(${columnLetter}${row},\",\",REPT(\" \",100)),ROW(INDIRECT(\"1:\"&LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},\",\",\"\"))+1))*100-99,100)),{${optionsList}},0)))=LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},\",\",\"\"))+1))`;
            }
            cell.dataValidation = {
              type: 'custom',
              allowBlank: !column.required,
              formulae: [formula],
              showErrorMessage: true,
              errorTitle: t('node-manager.cloudregion.integrations.error'),
              error: `${t('node-manager.cloudregion.integrations.pleaseSelectFromDropdown')}: ${validation.options.join(', ')}`,
              promptTitle: column.label,
              showInputMessage: true,
            };
          }
          continue;
        }

        if (column.type === 'inputNumber') {
          const min = column.widget_props?.min ?? 0;
          const max = column.widget_props?.max ?? 999999999;
          cell.dataValidation = {
            type: 'whole',
            operator: 'between',
            allowBlank: !column.required,
            formulae: [min, max],
            showErrorMessage: true,
            errorTitle: t('node-manager.cloudregion.integrations.error'),
            error: `${t('node-manager.cloudregion.integrations.mustBeNumber')} (${min}-${max})`,
            promptTitle: column.label,
            showInputMessage: true,
          };
          continue;
        }

        if (column.rules && column.rules.length > 0) {
          const patternRule = column.rules.find((rule) => rule.type === 'pattern');
          if (patternRule?.excel_formula) {
            let excelFormula = patternRule.excel_formula.replace(/\{\{CELL\}\}/g, `${columnLetter}${row}`);
            if (column.required) {
              excelFormula = `AND(LEN(${columnLetter}${row})>0,${excelFormula})`;
            } else {
              excelFormula = `OR(LEN(${columnLetter}${row})=0,${excelFormula})`;
            }
            cell.dataValidation = {
              type: 'custom',
              allowBlank: !column.required,
              formulae: [excelFormula],
              showErrorMessage: true,
              errorTitle: t('node-manager.cloudregion.integrations.error'),
              error: patternRule.message || t('common.formatError'),
              promptTitle: column.label,
              showInputMessage: true,
            };
          }
        }
      }
    });

    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${pluginName || 'integration'}-template.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleCancel = () => {
    setOpen(false);
    setTitle('');
    setFileList([]);
    setParsedData([]);
    setColumns([]);
    setNodeList([]);
    setGroupListProp([]);
    setPluginName('');
    setConfirmLoading(false);
  };

  return (
    <ImportFileModalShell
      title={title}
      open={open}
      width={640}
      confirmLoading={confirmLoading}
      onConfirm={handleSubmit}
      onCancel={handleCancel}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      footerExtra={
        <Button onClick={generateTemplate} icon={<DownloadOutlined />}>
          {t('common.downloadTemplate')}
        </Button>
      }
      uploadProps={{
        fileList: fileList as any[],
        onChange: handleChange,
        customRequest,
        accept: '.xlsx,.xls',
        maxCount: 1,
        icon: <CloudUploadOutlined />,
        uploadText: t('monitor.integrations.uploadExcel'),
        uploadHint: t('monitor.integrations.uploadExcelHint'),
      }}
    />
  );
});

IntegrationExcelImportModal.displayName = 'IntegrationExcelImportModal';

export default IntegrationExcelImportModal;
