'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
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

interface ModalConfig {
  title: string;
  columns: any[];
  nodeList?: any[];
  groupList?: any[];
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
    const [columns, setColumns] = useState<any[]>([]);
    const [nodeList, setNodeList] = useState<any[]>([]);
    const [groupListProp, setGroupListProp] = useState<any[]>([]);
    const [pluginName, setPluginName] = useState<string>('');
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
        return nodes.reduce((acc, node) => {
          const currentPath = parentPath
            ? `${parentPath}/${node.title}`
            : node.title;
          acc.push({
            label: currentPath, // 完整路径：父/子
            value: node.value,
            name: node.title, // 原始名称
            originalLabel: node.title, // 保存原始 label
          });
          if (node.children && node.children.length > 0) {
            acc.push(...flattenTree(node.children, currentPath));
          }
          return acc;
        }, [] as any[]);
      };
      return flattenTree(treeSelectData);
    }, [userContext?.groupTree]);

    // 优先使用传入的 groupList,否则使用默认值
    const groupList =
      groupListProp.length > 0 ? groupListProp : defaultGroupList;

    useImperativeHandle(ref, () => ({
      showModal: ({
        title,
        columns,
        nodeList = [],
        groupList = [],
        pluginName = '',
      }) => {
        setVisible(true);
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
      // 校验唯一性
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
      // 验证文件大小 (20MB)
      const maxSize = 20 * 1024 * 1024;
      if (file.size > maxSize) {
        message.error(t('monitor.integrations.fileSizeExceeded'));
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
            message.error(t('monitor.integrations.emptyExcelFile'));
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
          message.error(t('monitor.integrations.parseExcelFailed'));
          onError(error);
        }
      };
      reader.readAsArrayBuffer(file);
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
        return column.default_value;
      }
      const isMultiple = column.widget_props?.mode === 'multiple';
      // 根据列类型转换值
      switch (column.type) {
        case 'select':
          if (column.name === 'node_ids') {
            // 节点选择：根据 mode 判断是否支持多选
            if (isMultiple) {
              // 多选模式：格式为 "node1, node2"
              const nodeNames = value
                .toString()
                .split(',')
                .map((n: string) => n.trim());
              const nodeIds = nodeList
                .filter((node) => nodeNames.includes(node.label))
                .map((node) => node.value);
              return nodeIds.length > 0 ? nodeIds : null;
            } else {
              // 单选模式：直接匹配单个节点
              const nodeName = value.toString().trim();
              const node = nodeList.find((node) => node.label === nodeName);
              return node ? node.value : null;
            }
          }
          // 其他 select 类型也根据 mode 判断
          if (isMultiple) {
            // 多选：格式为 "选项1, 选项2"
            const valueStr = value.toString();
            const values = valueStr.split(',').map((v: string) => v.trim());
            return values;
          }
          return value;
        case 'group_select':
          // 组织选择：支持多选，格式为 "父/子, 父/子2"
          if (column.name === 'group_ids') {
            const groupNames = value
              .toString()
              .split(',')
              .map((g: string) => g.trim());
            // 从 groupList 中根据完整路径匹配 ID
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
      // 使用 exceljs 创建工作簿
      const workbook = new ExcelJS.Workbook();
      // 创建主工作表
      const mainSheet = workbook.addWorksheet(
        t('monitor.integrations.dataTemplate')
      );
      // 设置表头（添加多选提示）
      const headers = columns.map((col) => {
        const isMultiple =
          col.widget_props?.mode === 'multiple' || col.type === 'group_select';
        return isMultiple
          ? `${col.label} (${t('monitor.integrations.multipleSupport')})`
          : col.label;
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
        let optionsList: string[] = [];
        let sheetName = '';
        // 设置列宽
        mainSheet.getColumn(index + 1).width = 25;
        if (col.type === 'select' && col.name === 'node_ids') {
          // 节点列
          if (nodeList && nodeList.length > 0) {
            optionsList = nodeList.map((node) => node.label);
            sheetName = `${col.label}${t(
              'monitor.integrations.optionsSuffix'
            )}`;
          }
        } else if (col.type === 'group_select') {
          // 组织列，使用完整路径（父/子）
          if (groupList && groupList.length > 0) {
            optionsList = groupList.map(
              (group: any) => group.label || group.name
            );
            sheetName = `${col.label}${t(
              'monitor.integrations.optionsSuffix'
            )}`;
          }
        } else if (col.widget_props?.options) {
          // 其他带选项的列
          optionsList = col.widget_props.options.map((opt: any) => opt.label);
          sheetName = `${col.label}${t('monitor.integrations.optionsSuffix')}`;
        }
        // 如果有选项列表,创建选项工作表和数据验证
        if (optionsList.length > 0 && sheetName) {
          // 确保工作表名称不重复且符合 Excel 规范(最多31个字符)
          let finalSheetName = sheetName.substring(0, 31);
          let counter = 1;
          while (workbook.getWorksheet(finalSheetName)) {
            finalSheetName = `${sheetName.substring(0, 28)}_${counter}`;
            counter++;
          }
          // 创建选项工作表
          const optionsSheet = workbook.addWorksheet(finalSheetName);
          optionsList.forEach((opt) => {
            optionsSheet.addRow([opt]);
          });
          optionsSheet.getColumn(1).width = 30;
          // 记录列信息
          columnValidations.set(index, {
            sheetName: finalSheetName,
            options: optionsList,
          });
        }
      });
      // 为主工作表的数据列添加数据验证(仅单选列)
      columnValidations.forEach((validation, colIndex) => {
        const column = columns[colIndex];
        const isMultiple =
          column.widget_props?.mode === 'multiple' ||
          column.type === 'group_select';

        // 多选列不添加数据验证，允许自由输入逗号分隔的值
        if (isMultiple) {
          return;
        }

        // 单选列添加下拉数据验证
        const columnLetter = String.fromCharCode(65 + colIndex); // A, B, C...
        const optionsCount = validation.options.length;

        // 为第2行到第1001行添加数据验证
        for (let row = 2; row <= 1001; row++) {
          const cell = mainSheet.getCell(`${columnLetter}${row}`);
          // 添加数据验证 - 引用选项工作表
          cell.dataValidation = {
            type: 'list',
            allowBlank: true,
            formulae: [`'${validation.sheetName}'!$A$1:$A$${optionsCount}`],
            showErrorMessage: true,
            errorTitle: t('monitor.integrations.inputError'),
            error: t('monitor.integrations.selectFromDropdown'),
            promptTitle: column.label,
            showInputMessage: true,
          };
        }
      });
      // 为 is_only 字段添加条件格式，高亮显示重复值
      columns.forEach((col, index) => {
        if (col.is_only === true) {
          const columnLetter = String.fromCharCode(65 + index); // A, B, C...
          const range = `${columnLetter}2:${columnLetter}1001`;
          // 添加条件格式：检测重复值
          mainSheet.addConditionalFormatting({
            ref: range,
            rules: [
              {
                type: 'expression',
                priority: 1,
                formulae: [
                  `COUNTIF($${columnLetter}$2:$${columnLetter}$1001,${columnLetter}2)>1`,
                ],
                style: {
                  fill: {
                    type: 'pattern',
                    pattern: 'solid',
                    bgColor: { argb: 'FFFFC7CE' }, // 浅红色背景
                  },
                  font: {
                    color: { argb: 'FF9C0006' }, // 深红色文字
                  },
                },
              },
            ],
          });
          // 为表头添加注释提示
          const headerCell = mainSheet.getCell(`${columnLetter}1`);
          headerCell.note = {
            texts: [
              {
                font: { size: 10, name: 'Arial' },
                text: t('monitor.integrations.uniqueFieldTip'),
              },
            ],
            margins: {
              insetmode: 'auto',
              inset: [0.13, 0.13, 0.25, 0.25],
            },
          };
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
