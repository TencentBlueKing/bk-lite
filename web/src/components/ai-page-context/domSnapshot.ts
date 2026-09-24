import { isSecretControl, isSecretFieldLabel, readVisibleFormFacts } from './secretSnapshot';

export const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const ACTION_HEADER = /详情|关闭|Detail|Close|操作|编辑|删除|Edit|Delete/;
const OVERLAY_BODY_BUDGET = 3500;
const OVERLAY_SECTION_ID = 'page-overlay';

export const PAGE_OVERLAY_SECTION_ID = OVERLAY_SECTION_ID;

const isElementVisible = (el: Element | null | undefined): el is HTMLElement => {
  if (!(el instanceof HTMLElement)) return false;
  if (el.hidden || el.getAttribute('aria-hidden') === 'true') return false;
  if (typeof window === 'undefined') return true;
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  return true;
};

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

const readTreeNodeLabel = (node: Element): string => {
  const title = node.querySelector('.ant-tree-title');
  const meta = title?.querySelector('.treeMetaNode');
  if (meta) {
    const name = cleanLabel(meta.querySelector('[class*="label"]')?.textContent || '');
    const count = cleanLabel(meta.querySelector('[class*="count"]')?.textContent || '');
    if (name) return count ? `${name} (${count})` : name;
  }
  const wrapper = node.querySelector('.ant-tree-node-content-wrapper');
  return cleanLabel(title?.textContent || wrapper?.textContent || '');
};

/** 可见左侧树节点（含计数）；当前选中节点标 [当前]。无 .ant-tree 时返回空。 */
export const readTreeLines = (root?: Element | Document | null): string[] => {
  const scope = root || document;
  const tree = scope.querySelector?.('.ant-tree');
  if (!tree) return [];
  return Array.from(tree.querySelectorAll('.ant-tree-treenode'))
    .map((node) => {
      const label = readTreeNodeLabel(node);
      if (!label) return '';
      const selected = node.classList.contains('ant-tree-treenode-selected')
        || Boolean(node.querySelector('.ant-tree-node-selected'));
      const depth = node.querySelectorAll('.ant-tree-indent-unit').length;
      const indent = depth > 0 ? `${'  '.repeat(depth)}` : '';
      return `${indent}${label}${selected ? ' [当前]' : ''}`;
    })
    .filter(Boolean);
};

export const treeSection = (root?: Element | Document | null) => {
  const lines = readTreeLines(root);
  return lines.length
    ? [{
      id: 'page-tree',
      label: '左侧树',
      content: lines.join('\n'),
      priority: 9,
    }]
    : [];
};

const isSecretFormItem = (item: Element): boolean => {
  if (isSecretControl(item)) return true;
  const label = cleanLabel(item.querySelector('label')?.textContent || '').replace(/[:：]\s*$/, '');
  return isSecretFieldLabel(label);
};

/** 弹窗 / Drawer 内未包在 Form.Item 里的控件值（指标配置等多列 Select+Input）。 */
const readLooseControlLines = (root: Element): string[] => {
  const lines: string[] = [];

  root.querySelectorAll('.ant-select').forEach((select) => {
    if (select.closest('.ant-pagination, .ant-table-filter-trigger')) return;
    // Form.Item 内的 Select 由 readVisibleFormFacts 负责，避免密钥项被二次写入。
    if (select.closest('.ant-form-item')) return;
    const item = cleanLabel(select.querySelector('.ant-select-selection-item')?.textContent || '');
    if (item) lines.push(item);
  });

  root.querySelectorAll('input, textarea').forEach((node) => {
    const input = node as HTMLInputElement | HTMLTextAreaElement;
    if (
      input.type === 'password'
      || input.type === 'hidden'
      || input.type === 'checkbox'
      || input.type === 'radio'
      || input.closest('.ant-select, .ant-input-password, .ant-pagination, .ant-picker')
    ) {
      return;
    }
    // Form.Item 值只走 readVisibleFormFacts，避免密钥标签项经松散路径回流。
    const formItem = input.closest('.ant-form-item');
    if (formItem) return;
    const placeholder = cleanLabel(input.getAttribute('placeholder') || '');
    if (isSecretFieldLabel(placeholder)) return;
    const value = cleanLabel(input.value || '');
    if (!value) return;
    lines.push(placeholder ? `${placeholder}: ${value}` : value);
  });

  root.querySelectorAll('.ant-collapse-item').forEach((item) => {
    const header = cleanLabel(item.querySelector('.ant-collapse-header')?.textContent || '');
    if (header) lines.push(`分组: ${header}`);
  });

  return lines;
};

const cleanOverlayInnerText = (body: Element): string => {
  const clone = body.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('.ant-form-item').forEach((item) => {
    if (isSecretFormItem(item)) item.remove();
  });
  clone.querySelectorAll('input, textarea').forEach((node) => {
    const input = node as HTMLInputElement | HTMLTextAreaElement;
    const placeholder = cleanLabel(input.getAttribute('placeholder') || '');
    if (
      input.type === 'password'
      || input.closest('.ant-input-password')
      || isSecretFieldLabel(placeholder)
    ) {
      node.remove();
    }
  });
  clone.querySelectorAll(
    '.ant-input-password, .ant-modal-close, .ant-drawer-close, script, style',
  ).forEach((node) => node.remove());
  return cleanLabel((clone.textContent || '').replace(/\n+/g, '\n')).slice(0, OVERLAY_BODY_BUDGET);
};

export const findVisibleOverlayRoots = (): Array<{ kind: 'modal' | 'drawer'; root: Element }> => {
  if (typeof document === 'undefined') return [];
  const out: Array<{ kind: 'modal' | 'drawer'; root: Element }> = [];

  document.querySelectorAll('.ant-modal-wrap').forEach((wrap) => {
    if (!isElementVisible(wrap)) return;
    const modal = wrap.querySelector('.ant-modal');
    if (modal) out.push({ kind: 'modal', root: modal });
  });

  document.querySelectorAll('.ant-drawer.ant-drawer-open').forEach((drawer) => {
    const content = drawer.querySelector('.ant-drawer-content') || drawer;
    if (!isElementVisible(drawer) && !isElementVisible(drawer.querySelector('.ant-drawer-content-wrapper'))) {
      return;
    }
    out.push({ kind: 'drawer', root: content });
  });

  return out;
};

export const readOverlayBlocks = (): string[] => {
  return findVisibleOverlayRoots().map(({ kind, root }) => {
    const title = cleanLabel(
      root.querySelector('.ant-modal-title, .ant-drawer-title')?.textContent || '',
    );
    const body = root.querySelector('.ant-modal-body, .ant-drawer-body') || root;
    const structured = [
      ...readVisibleFormFacts(body),
      ...readTableRows(body),
      ...readTreeLines(body),
      ...readLooseControlLines(body),
    ].filter(Boolean);
    const unique: string[] = [];
    const seen = new Set<string>();
    for (const line of structured) {
      if (seen.has(line)) continue;
      seen.add(line);
      unique.push(line);
    }
    const bodyText = (unique.length ? unique.join('\n') : cleanOverlayInnerText(body))
      .slice(0, OVERLAY_BODY_BUDGET);
    const kindLabel = kind === 'drawer' ? '侧边栏' : '弹窗';
    return [`[${kindLabel}] ${title || '未命名'}`, bodyText].filter(Boolean).join('\n');
  }).filter((block) => block.replace(/\s+/g, '').length > 4);
};

/** 可见 Ant Design Modal / Drawer；priority 高于页面列表，避免被表格挤掉。 */
export const overlaySection = () => {
  const blocks = readOverlayBlocks();
  return blocks.length
    ? [{
      id: OVERLAY_SECTION_ID,
      label: '弹窗与侧边栏',
      content: blocks.join('\n\n'),
      priority: 11,
    }]
    : [];
};

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
