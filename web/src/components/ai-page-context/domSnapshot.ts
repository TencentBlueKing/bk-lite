export const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const ACTION_HEADER = /详情|关闭|Detail|Close|操作|编辑|删除|Edit|Delete/;

export const readTableRows = (root?: Element | Document | null): string[] => {
  const table = (root || document).querySelector?.('.ant-table')
    || (root || document).querySelector?.('table');
  if (!table) return [];
  const headerCells = Array.from(table.querySelectorAll('thead th')).map((cell, index, all) => {
    if (index === all.length - 1 && ACTION_HEADER.test(cell.textContent || '')) return '';
    return cleanLabel(cell.textContent || '');
  });
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row, .ant-table-tbody tr'))
    .filter((row) => !row.classList.contains('ant-table-measure-row'))
    .map((row) => {
      const cells = Array.from(row.querySelectorAll('td'));
      const usable = cells.filter((cell) => !cell.querySelector('button, .ant-btn, a.ant-btn'));
      return usable.map((cell) => cleanLabel(cell.textContent || '')).filter(Boolean).join(' | ');
    })
    .filter(Boolean);
  return [header, ...bodyRows].filter(Boolean);
};

export const readPaginationRange = (root?: Element | Document | null): string => {
  const scope = root || document;
  const total = cleanLabel(scope.querySelector?.('.ant-pagination-total-text')?.textContent || '');
  const page = cleanLabel(scope.querySelector?.('.ant-pagination-item-active')?.textContent || '');
  return [total, page ? `当前第 ${page} 页` : ''].filter(Boolean).join('；');
};

export const selectedTreeLabel = (): string =>
  cleanLabel(document.querySelector('.ant-tree-node-selected')?.textContent || '');

export const selectedSegmentedValue = (root?: Element | Document | null): string => {
  const selected = (root || document).querySelector?.('.ant-segmented-item-selected');
  if (!selected) return '';
  const input = selected.querySelector('input');
  const value = input?.getAttribute('value') || input?.value || '';
  return value || cleanLabel(selected.textContent || '');
};

export const visibleChartsSection = (captions: string[]) =>
  captions.length
    ? [{
      id: 'visible-charts',
      label: '可见图表',
      content: captions.map((caption, index) => `${index + 1}. ${caption}`).join('\n'),
      priority: 9,
    }]
    : [];
