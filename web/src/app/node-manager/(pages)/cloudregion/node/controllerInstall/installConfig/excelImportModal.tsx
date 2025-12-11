'use client';
import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
} from 'react';
import { Button, Upload, message } from 'antd';
import type { UploadProps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/app/monitor/components/operate-drawer';
import { CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import ExcelJS from 'exceljs';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils';

interface ExcelImportModalProps {
  onSuccess: (data: any[]) => void;
}

interface ModalConfig {
  title: string;
  columns: any[];
  groupList?: any[];
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
    const [columns, setColumns] = useState<any[]>([]);
    const [groupListProp, setGroupListProp] = useState<any[]>([]);
    const { t } = useTranslation();
    const { Dragger } = Upload;
    const userContext = useUserInfoContext();

    // 默认从 userContext 获取组织列表
    const defaultGroupList = useMemo(() => {
      if (!userContext?.groupTree) return [];
      const treeSelectData = convertGroupTreeToTreeSelectData(
        userContext.groupTree
      );
      // 递归提取所有组织节点，包含完整路径
      const flattenTree = (nodes: any[], parentPath = ''): any[] => {
        return nodes.reduce((acc: any[], node: any) => {
          const currentPath = parentPath
            ? `${parentPath} / ${node.label}`
            : node.label;
          const current = {
            value: node.value,
            label: currentPath,
          };
          if (node.children && node.children.length > 0) {
            return [
              ...acc,
              current,
              ...flattenTree(node.children, currentPath),
            ];
          }
          return [...acc, current];
        }, []);
      };
      return flattenTree(treeSelectData);
    }, [userContext?.groupTree]);

    // 优先使用传入的 groupList,否则使用默认值
    const groupList =
      groupListProp.length > 0 ? groupListProp : defaultGroupList;

    useImperativeHandle(ref, () => ({
      showModal: ({ title, columns, groupList = [] }) => {
        setVisible(true);
        setTitle(title);
        setFileList([]);
        setParsedData([]);
        setColumns(columns);
        setGroupListProp(groupList);
      },
    }));

    const handleSubmit = () => {
      if (!parsedData || parsedData.length === 0) {
        message.error(
          t('node-manager.cloudregion.integrations.noDataToImport')
        );
        return;
      }
      // 校验字段规则
      const fieldValidationResult = validateFields(parsedData);
      if (!fieldValidationResult.isValid) {
        message.error(
          fieldValidationResult.errorMsg || t('common.fieldRequired')
        );
        return;
      }
      // 校验唯一性
      const uniqueCheckResult = validateUniqueness(parsedData);
      if (!uniqueCheckResult.isValid) {
        message.error(
          `${uniqueCheckResult.field || ''}: ${
            uniqueCheckResult.value || ''
          } ${t('common.duplicate')}`
        );
        return;
      }
      setConfirmLoading(true);
      try {
        onSuccess(parsedData);
        const successMsg = `${t(
          'node-manager.cloudregion.integrations.importSuccess'
        )} (${parsedData.length})`;
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
      // 验证文件大小 (20MB)
      const maxSize = 20 * 1024 * 1024;
      if (file.size > maxSize) {
        message.error(
          t('node-manager.cloudregion.integrations.fileSizeExceeded')
        );
        onError(new Error('File size exceeded'));
        return;
      }
      // 使用 exceljs 解析 Excel 文件
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const buffer = e.target?.result as ArrayBuffer;
          const workbook = new ExcelJS.Workbook();
          await workbook.xlsx.load(buffer);
          const firstSheet = workbook.worksheets[0];
          if (!firstSheet || firstSheet.rowCount < 2) {
            message.error(
              t('node-manager.cloudregion.integrations.noDataToImport')
            );
            onError(new Error('Empty file'));
            return;
          }
          // 解析表头和数据
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
          // 将数据转换为对象数组
          const parsedRows = rows
            .filter((row) => row.some((cell) => cell !== null && cell !== ''))
            .map((row) => {
              const rowData: any = {};
              headers.forEach((header, index) => {
                // 去掉表头中的后缀提示，如 "(支持多个，用逗号分隔)"
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
          message.error(
            t('node-manager.cloudregion.integrations.parseExcelFailed')
          );
          onError(error);
        }
      };
      reader.readAsArrayBuffer(file);
    };

    // 校验字段规则
    const validateFields = (
      data: any[]
    ): { isValid: boolean; errorMsg?: string } => {
      for (let rowIndex = 0; rowIndex < data.length; rowIndex++) {
        const row = data[rowIndex];
        for (const column of columns) {
          const { name, label, required = false, rules = [] } = column;
          const value = row[name];
          // 必填验证
          if (required) {
            if (
              value === undefined ||
              value === null ||
              value === '' ||
              (Array.isArray(value) && value.length === 0)
            ) {
              return {
                isValid: false,
                errorMsg: `${t('node-manager.cloudregion.integrations.row')} ${
                  rowIndex + 1
                }: ${label} ${t('common.required')}`,
              };
            }
          }
          // 正则验证（只在有值时验证）
          if (rules.length > 0) {
            for (const rule of rules) {
              if (rule.type === 'pattern') {
                if (value !== undefined && value !== null && value !== '') {
                  const stringValue = String(value?.text || value || '').trim();
                  const regex = new RegExp(rule.pattern);
                  if (!regex.test(stringValue)) {
                    return {
                      isValid: false,
                      errorMsg: `${t(
                        'node-manager.cloudregion.integrations.row'
                      )} ${rowIndex + 1}: ${label} ${
                        rule.message || t('common.required')
                      }`,
                    };
                  }
                }
              }
            }
          }
        }
      }
      return { isValid: true };
    };

    // 校验唯一性
    const validateUniqueness = (
      data: any[]
    ): { isValid: boolean; field?: string; value?: string } => {
      // 查找所有需要校验唯一性的字段
      const uniqueFields = columns.filter((col) => col.is_only === true);
      for (const field of uniqueFields) {
        const fieldName = field.name;
        const fieldLabel = field.label;
        const valueSet = new Set<string>();
        for (const row of data) {
          const value = row[fieldName];
          // 跳过空值
          if (value === null || value === undefined || value === '') {
            continue;
          }
          const valueStr = String(value);
          if (valueSet.has(valueStr)) {
            return {
              isValid: false,
              field: fieldLabel,
              value: valueStr,
            };
          }
          valueSet.add(valueStr);
        }
      }
      return { isValid: true };
    };

    // 转换单元格值
    const transformCellValue = (value: any, column: any) => {
      if (value === null || value === undefined || value === '') {
        return column.default_value !== undefined ? column.default_value : null;
      }
      // 根据列类型转换值
      switch (column.type) {
        case 'inputNumber':
          return typeof value === 'number' ? value : Number(value);
        case 'group_select':
          // 处理组织选择（默认多选）
          const groupValues = String(value?.text || value)
            .split(',')
            .map((v) => v.trim());
          return groupValues
            .map((v) => {
              const group = groupList.find((g: any) => g.label === v);
              return group ? group.value : null;
            })
            .filter(Boolean);
        case 'select':
          // 处理下拉选择
          const isMultiple = column.widget_props?.mode === 'multiple';
          const selectValue = String(value?.text || value);
          if (isMultiple) {
            return selectValue.split(',').map((v) => v.trim());
          }
          return selectValue;
        default:
          return String(value?.text || value);
      }
    };

    const handleDownloadTemplate = async () => {
      // 使用 exceljs 创建工作簿
      const workbook = new ExcelJS.Workbook();
      // 创建主工作表
      const mainSheet = workbook.addWorksheet(
        t('node-manager.cloudregion.integrations.dataTemplate')
      );
      // 设置表头（添加多选提示）
      const headers = columns.map((col) => {
        const isMultiple =
          col.widget_props?.mode === 'multiple' || col.type === 'group_select';
        const baseLabel = col.label;
        return isMultiple
          ? `${baseLabel} (${t(
            'node-manager.cloudregion.integrations.multipleSelectHint'
          )})`
          : baseLabel;
      });
      mainSheet.addRow(headers);
      // 设置表头样式
      mainSheet.getRow(1).font = { bold: true };
      mainSheet.getRow(1).fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FFE0E0E0' },
      };
      // 存储每列的数据验证信息
      const columnValidations: Map<
        number,
        { sheetName: string; options: string[] }
      > = new Map();
      // 为每个有选项的列处理数据验证
      columns.forEach((col, index) => {
        // 设置列宽
        mainSheet.getColumn(index + 1).width = 25;

        const colIndex = index + 1;
        if (col.type === 'group_select') {
          const options = groupList.map((g: any) => g.label);
          if (options.length > 0) {
            const sheetName = `${col.label}_${t(
              'node-manager.cloudregion.integrations.options'
            )}`;
            const optionsSheet = workbook.addWorksheet(sheetName);
            // 从第一行开始添加选项数据（不添加空行）
            options.forEach((opt) => {
              optionsSheet.addRow([opt]);
            });
            optionsSheet.getColumn(1).width = 30;
            optionsSheet.state = 'hidden';
            columnValidations.set(colIndex, { sheetName, options });
          }
        }
      });
      // 为主工作表的数据列添加数据验证
      columns.forEach((column, colIndex) => {
        const columnLetter = String.fromCharCode(65 + colIndex); // A, B, C...
        const validation = columnValidations.get(colIndex + 1);

        // 为第2行到第1001行添加数据验证
        for (let row = 2; row <= 1001; row++) {
          const cell = mainSheet.getCell(`${columnLetter}${row}`);

          // 1. 必填验证（优先级最高，文本长度检查）
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

          // 2. 下拉列表验证（单选/多选）
          if (validation) {
            const isMultiple =
              column.widget_props?.mode === 'multiple' ||
              column.type === 'group_select';
            if (!isMultiple) {
              // 单选：使用标准下拉列表验证
              cell.dataValidation = {
                type: 'list',
                allowBlank: !column.required,
                formulae: [
                  `'${validation.sheetName}'!$A$1:$A$${validation.options.length}`,
                ],
                showErrorMessage: true,
                errorTitle: t('node-manager.cloudregion.integrations.error'),
                error: t(
                  'node-manager.cloudregion.integrations.pleaseSelectFromDropdown'
                ),
                promptTitle: column.label,
                showInputMessage: true,
              };
            } else {
              // 多选：使用自定义公式验证逗号分隔的值
              const optionsList = validation.options
                .map((opt) => `"${opt}"`)
                .join(',');
              // 构建验证公式：检查单元格中每个逗号分隔的值是否在选项列表中
              let formula = '';
              if (column.required) {
                // 必填：要求非空且所有值都在选项中
                formula = `AND(LEN(${columnLetter}${row})>0,SUMPRODUCT(--ISNUMBER(MATCH(TRIM(MID(SUBSTITUTE(${columnLetter}${row},",",REPT(" ",100)),ROW(INDIRECT("1:"&LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1))*100-99,100)),{${optionsList}},0)))=LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1)`;
              } else {
                // 非必填：允许空值或所有值都在选项中
                formula = `OR(LEN(${columnLetter}${row})=0,AND(LEN(${columnLetter}${row})>0,SUMPRODUCT(--ISNUMBER(MATCH(TRIM(MID(SUBSTITUTE(${columnLetter}${row},",",REPT(" ",100)),ROW(INDIRECT("1:"&LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1))*100-99,100)),{${optionsList}},0)))=LEN(${columnLetter}${row})-LEN(SUBSTITUTE(${columnLetter}${row},",",""))+1))`;
              }
              cell.dataValidation = {
                type: 'custom',
                allowBlank: !column.required,
                formulae: [formula],
                showErrorMessage: true,
                errorTitle: t('node-manager.cloudregion.integrations.error'),
                error: `${t(
                  'node-manager.cloudregion.integrations.pleaseSelectFromDropdown'
                )}: ${validation.options.join(', ')}`,
                promptTitle: column.label,
                showInputMessage: true,
              };
            }
            continue;
          }

          // 3. 数字类型验证
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
              error: `${t(
                'node-manager.cloudregion.integrations.mustBeNumber'
              )} (${min}-${max})`,
              promptTitle: column.label,
              showInputMessage: true,
            };
            continue;
          }

          // 4. 正则表达式验证（使用JSON中配置的Excel公式）
          if (column.rules && column.rules.length > 0) {
            const patternRule = column.rules.find(
              (r: any) => r.type === 'pattern'
            );
            if (patternRule && patternRule.excel_formula) {
              // 使用配置中的excel_formula，替换CELL占位符
              let excelFormula = patternRule.excel_formula.replace(
                /\{\{CELL\}\}/g,
                `${columnLetter}${row}`
              );
              // 如果是必填，需要加上非空判断
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
              continue;
            }
          }
        }
      });
      // 生成文件并下载
      const buffer = await workbook.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${t(
        'node-manager.cloudregion.node.installController'
      )}_${t('node-manager.cloudregion.integrations.template')}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
    };

    const handleCancel = () => {
      setVisible(false);
      setFileList([]);
      setParsedData([]);
    };

    const beforeUpload = (file: File) => {
      const isExcel =
        file.type ===
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
        file.type === 'application/vnd.ms-excel';
      if (!isExcel) {
        message.error(
          t('node-manager.cloudregion.integrations.onlyExcelAllowed')
        );
      }
      const maxSize = 20 * 1024 * 1024;
      if (file.size > maxSize) {
        message.error(
          t('node-manager.cloudregion.integrations.fileSizeExceeded')
        );
      }
      return isExcel && file.size <= maxSize;
    };

    return (
      <OperateModal
        title={title}
        visible={visible}
        onClose={handleCancel}
        width={600}
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
        <div>
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
              <Button type="link">
                {t('node-manager.cloudregion.integrations.clickUpload')}
              </Button>
            </p>
          </Dragger>
        </div>
        <div className="mt-[16px]">
          <p className="text-[12px] text-[var(--color-text-3)]">
            {t('node-manager.cloudregion.integrations.excelImportTips')}
          </p>
          <Button
            className="p-0"
            icon={<DownloadOutlined />}
            onClick={handleDownloadTemplate}
            type="link"
          >
            {t('node-manager.cloudregion.integrations.downloadTemplate')}
          </Button>
        </div>
      </OperateModal>
    );
  }
);

ExcelImportModal.displayName = 'ExcelImportModal';
export default ExcelImportModal;
