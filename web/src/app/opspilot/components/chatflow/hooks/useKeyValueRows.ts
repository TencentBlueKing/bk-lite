import { useState, useCallback } from 'react';

export interface KeyValueRow {
  key: string;
  value: string;
}

export const useKeyValueRows = (initialRows: KeyValueRow[] = []) => {
  const [rows, setRows] = useState<KeyValueRow[]>(initialRows);

  const addRow = useCallback(() => {
    setRows(prev => [...prev, { key: '', value: '' }]);
  }, []);

  const removeRow = useCallback((index: number) => {
    setRows(prev => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev);
  }, []);

  const updateRow = useCallback((index: number, field: 'key' | 'value', value: string) => {
    setRows(prev => {
      const newRows = [...prev];
      newRows[index][field] = value;
      return newRows;
    });
  }, []);

  const resetRows = useCallback((newRows: KeyValueRow[]) => {
    setRows(newRows);
  }, []);

  return { rows, addRow, removeRow, updateRow, resetRows };
};
