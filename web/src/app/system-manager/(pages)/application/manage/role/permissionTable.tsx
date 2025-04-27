import React, { useState } from 'react';
import { Checkbox, TableProps } from 'antd';
import CustomTable from '@/components/custom-table';
import { CheckboxChangeEvent } from 'antd/es/checkbox';
import { Menu } from '@/app/system-manager/types/application';

type TranslateFunction = (key: string) => string;

interface PermissionTableProps {
  menuData: Menu[];
  loading: boolean;
  permissionsCheckedKeys: Record<string, string[]>;
  setPermissionsCheckedKeys: React.Dispatch<React.SetStateAction<Record<string, string[]>>>;
  t: TranslateFunction;
}

const PermissionTable: React.FC<PermissionTableProps> = ({
  menuData,
  loading,
  permissionsCheckedKeys,
  setPermissionsCheckedKeys,
  t
}) => {
  const [expandedKeys, setExpandedKeys] = useState<string[]>(menuData.map((item) => item.name));

  const getAllOperationKeys = (record: Menu): string[] => {
    let keys: string[] = [];
    if (record.operation) {
      keys = keys.concat(record.operation);
    }
    if (record.children) {
      record.children.forEach((child) => {
        keys = keys.concat(getAllOperationKeys(child));
      });
    }
    return keys;
  };

  const updateCheckedKeys = (record: Menu, checked: boolean, prevState: Record<string, string[]>): Record<string, string[]> => {
    const newCheckedKeys = { ...prevState };

    const handleOperations = (key: string, operations?: string[], isChecked?: boolean) => {
      if (!operations) return;
      if (isChecked) {
        newCheckedKeys[key] = [...new Set([...(newCheckedKeys[key] || []), ...operations])];
      } else {
        newCheckedKeys[key] = [];
      }
    };

    const handleChildren = (nodes: Menu[], isChecked: boolean) => {
      nodes.forEach((node) => {
        handleOperations(node.name, node.operation, isChecked);
        if (node.children) {
          handleChildren(node.children, isChecked);
        }
      });
    };
    handleChildren([record], checked);

    return newCheckedKeys;
  };

  const handleMenuCheckboxChange = (record: Menu, checked: boolean) => {
    setPermissionsCheckedKeys((prevState) => {
      const newCheckedKeys = updateCheckedKeys(record, checked, prevState);
      return newCheckedKeys;
    });
  };

  const handleOperationCheckboxChange = (menuKey: string, operation: string, checked: boolean) => {
    setPermissionsCheckedKeys((prevState) => {
      let newCheckedKeys = { ...prevState };

      if (checked) {
        newCheckedKeys = {
          ...newCheckedKeys,
          [menuKey]: [...(newCheckedKeys[menuKey] || []), operation],
        };

        if (operation !== 'View' && !newCheckedKeys[menuKey].includes('View')) {
          newCheckedKeys[menuKey].push('View');
        }
      } else {
        newCheckedKeys[menuKey] = (newCheckedKeys[menuKey] || []).filter(op => op !== operation);

        if (operation === 'View') {
          newCheckedKeys[menuKey] = [];
        }
      }

      return newCheckedKeys;
    });
  };

  const isIndeterminate = (record: Menu): boolean => {
    const allKeys = getAllOperationKeys(record);
    const selectedKeys: string[] = [];
    if (permissionsCheckedKeys[record.name]) {
      selectedKeys.push(...permissionsCheckedKeys[record.name]);
    }
    record.children?.forEach(child => {
      if (permissionsCheckedKeys[child.name]) {
        selectedKeys.push(...permissionsCheckedKeys[child.name]);
      }
    });
    return selectedKeys.length > 0 && selectedKeys.length < allKeys.length;
  };

  const isChecked = (record: Menu): boolean => {
    const allKeys = getAllOperationKeys(record);
    const selectedKeys: string[] = [];
    if (permissionsCheckedKeys[record.name]) {
      selectedKeys.push(...permissionsCheckedKeys[record.name]);
    }
    record.children?.forEach((child) => {
      if (permissionsCheckedKeys[child.name]) {
        selectedKeys.push(...permissionsCheckedKeys[child.name]);
      }
    });
    return selectedKeys.length === allKeys.length;
  };

  const columns: TableProps<Menu>['columns'] = [
    {
      title: t('system.role.permission.menu'),
      dataIndex: 'display_name',
      width: '380px',
      key: 'display_name',
      render: (text: string, record: Menu) => (
        <Checkbox
          key={record.name}
          indeterminate={isIndeterminate(record)}
          onChange={(e: CheckboxChangeEvent) => handleMenuCheckboxChange(record, e.target.checked)}
          checked={isChecked(record)}
        >
          {text || record.name}
        </Checkbox>
      ),
    },
    {
      title: t('system.role.permission.operation'),
      dataIndex: 'operation',
      key: 'operation',
      render: (operations: string[], record: Menu) => (
        <div className="flex space-x-2" key={record.name}>
          {(operations || []).map((operation: string) => (
            <Checkbox
              key={operation}
              onChange={(e: CheckboxChangeEvent) => handleOperationCheckboxChange(record.name, operation, e.target.checked)}
              checked={permissionsCheckedKeys[record.name]?.includes(operation) || false}
            >
              {operation}
            </Checkbox>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className='flex w-full overflow-y-auto' style={{ height: 'calc(100vh - 335px)' }}>
      <CustomTable
        loading={loading}
        columns={columns}
        dataSource={menuData.map(item => ({ ...item, key: item.name }))}
        expandable={{
          childrenColumnName: 'children',
          expandedRowKeys: expandedKeys,
          onExpand: (expanded, record) => {
            setExpandedKeys((prev) =>
              expanded ? [...prev, record.name] : prev.filter((key) => key !== record.name)
            );
          },
        }}
        pagination={false}
      />
    </div>
  );
};

export default PermissionTable;
