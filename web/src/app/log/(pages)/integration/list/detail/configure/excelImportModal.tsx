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
        const successMsg = t('monitor.integrations.importSuccessCount').replace(
          '{{count}}',
          parsedData.length.toString()
        );
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
          // Parse headers and data
          const headers: string[] = [];
          firstSheet.getRow(1).eachCell((cell) => {
            headers.push(cell.value?.toString() || '');
          });
          const rows: any[][] = [];
          for (let i = 2; i <= firstSheet.rowCount; i++) {
            const row: any[] = [];
            firstSheet
              .getRow(i)
              .eachCell({ includeEmpty: true }, (cell, colNumber) => {
                row[colNumber - 1] = cell.value;
              });
            rows.push(row);
          }
          // Convert data to object array
          const parsedRows = rows
            .filter((row) => row.some((cell) => cell !== null && cell !== ''))
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

    // Transform cell value based on column type
    const transformCellValue = (value: any, column: ColumnConfig) => {
      if (value === null || value === undefined || value === '') {
        return column.default_value;
      }
      const isMultiple = column.widget_props?.mode === 'multiple';
      // Convert value based on column type
      switch (column.type) {
        case 'select':
          if (column.name === 'node_ids') {
            // Node selection: single select
            const nodeName = value.toString().trim();
            const node = nodeList.find((n) => n.label === nodeName);
            return node ? node.value : null;
          }
          // Other select types based on mode
          if (isMultiple) {
            const valueStr = value.toString();
            const values = valueStr.split(',').map((v: string) => v.trim());
            return values;
          }
          return value;
        case 'group_select':
          // Group selection: supports multiple, format "parent/child, parent/child2"
          if (column.name === 'group_ids') {
            const groupNames = value
              .toString()
              .split(',')
              .map((g: string) => g.trim());
            // Match IDs from groupList based on full path
            const groupIds = groupList
              .filter((group) => {
                const fullPath = group.label || group.name;
                return groupNames.includes(fullPath);
              })
              .map((group) => group.value);
            return groupIds.length > 0 ? groupIds : [];
          }
          return value;
        case 'inputNumber':
          return Number(value);
        default:
          return value;
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
        // If there's an options list, create options sheet and data validation
        if (optionsList.length > 0 && sheetName) {
          // Ensure sheet name is unique and conforms to Excel specs (max 31 chars)
          let finalSheetName = sheetName.substring(0, 31);
          let counter = 1;
          while (workbook.getWorksheet(finalSheetName)) {
            finalSheetName = `${sheetName.substring(0, 28)}_${counter}`;
            counter++;
          }
          // Create options sheet
          const optionsSheet = workbook.addWorksheet(finalSheetName);
          optionsList.forEach((opt) => {
            optionsSheet.addRow([opt]);
          });
          optionsSheet.getColumn(1).width = 30;
          // Record column info
          columnValidations.set(index, {
            sheetName: finalSheetName,
            options: optionsList
          });
        }
      });
      // Add data validation for main sheet columns
      columns.forEach((column, colIndex) => {
        const columnLetter = String.fromCharCode(65 + colIndex);
        const validation = columnValidations.get(colIndex);
        // Add data validation for rows 2 to 1001
        for (let row = 2; row <= 1001; row++) {
          const cell = mainSheet.getCell(`${columnLetter}${row}`);
          // Required validation (highest priority, text length check)
          if (column.required && !validation && column.type !== 'inputNumber') {
            cell.dataValidation = {
              type: 'textLength',
              operator: 'greaterThan',
              allowBlank: false,
              formulae: [0],
              showErrorMessage: true,
              errorTitle: t('monitor.integrations.inputError'),
              error: t('common.required'),
              promptTitle: column.label,
              showInputMessage: true
            };
            continue;
          }
          // Dropdown list validation (single/multiple select)
          if (validation) {
            const isMultiple =
              column.widget_props?.mode === 'multiple' ||
              column.type === 'group_select';
            if (!isMultiple) {
              // Single select: use standard dropdown validation
              cell.dataValidation = {
                type: 'list',
                allowBlank: !column.required,
                formulae: [
                  `'${validation.sheetName}'!$A$1:$A$${validation.options.length}`
                ],
                showErrorMessage: true,
                errorTitle: t('monitor.integrations.inputError'),
                error: t('monitor.integrations.selectFromDropdown'),
                promptTitle: column.label,
                showInputMessage: true
              };
            } else {
              // Multiple select: use custom formula validation for comma-separated values
              const optionsList = validation.options
                .map((opt) => `"${opt}"`)
                .join(',');
              const formula = `OR(LEN(${columnLetter}${row})=0,AND(LEN(${columnLetter}${row})>0,SUMPRODUCT(--ISNUMBER(MATCH(TRIM(MID(SUBSTITUTE(${columnLetter}${row},",",REPT(" ",100)),ROW(INDIRECT("1:"&LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1))*100-99,100)),{${optionsList}},0)))=LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1))`;
              cell.dataValidation = {
                type: 'custom',
                allowBlank: !column.required,
                formulae: [formula],
                showErrorMessage: true,
                errorTitle: t('monitor.integrations.inputError'),
                error: t(
                  'monitor.integrations.multipleValidationError'
                ).replace('{{options}}', validation.options.join(', ')),
                promptTitle: column.label,
                showInputMessage: true
              };
            }
            continue;
          }
          // Number type validation
          if (column.type === 'inputNumber') {
            const min = column.widget_props?.min ?? 0;
            const max = column.widget_props?.max ?? 999999999;
            cell.dataValidation = {
              type: 'whole',
              operator: 'between',
              allowBlank: !column.required,
              formulae: [min, max],
              showErrorMessage: true,
              errorTitle: t('monitor.integrations.inputError'),
              error: t('monitor.integrations.numberRangeError')
                .replace('{{min}}', min.toString())
                .replace('{{max}}', max.toString()),
              promptTitle: column.label,
              showInputMessage: true,
              prompt: t('monitor.integrations.numberRangeError')
                .replace('{{min}}', min.toString())
                .replace('{{max}}', max.toString())
            };
            continue;
          }
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
