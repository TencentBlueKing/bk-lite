import type { Node } from '@antv/x6';

export const SINGLE_VALUE_ERROR_PLACEHOLDER = '--';

const getSingleValueValueRefY = (node: Node) => {
  const hasName = Boolean(node.getData()?.name?.trim());
  return hasName ? '38%' : '50%';
};

const showFetchErrorIcon = (node: Node) => {
  const valueRefY = getSingleValueValueRefY(node);
  const fontSize = node.getAttrByPath('label/fontSize');
  node.setAttrByPath('label/display', 'none');
  node.setAttrByPath('errorIcon/refY', valueRefY);
  if (fontSize !== undefined) {
    node.setAttrByPath('errorIcon/fontSize', fontSize);
  }
  node.setAttrByPath('errorIcon/display', 'block');
};

const hideFetchErrorIcon = (node: Node) => {
  node.setAttrByPath('errorIcon/display', 'none');
  node.setAttrByPath('label/display', 'block');
};

export const showSingleValueFetchError = (
  node: Node,
  errorMessage: string,
): void => {
  node.setData(
    {
      ...node.getData(),
      isLoading: false,
      hasError: true,
      fetchError: true,
      errorMessage,
    },
    { overwrite: true },
  );
  showFetchErrorIcon(node);
};

export const clearSingleValueFetchError = (node: Node): void => {
  node.setData(
    {
      ...node.getData(),
      hasError: false,
      fetchError: false,
      errorMessage: undefined,
    },
    { overwrite: true },
  );
  hideFetchErrorIcon(node);
};

export const resetSingleValueFetchErrorVisual = (node: Node): void => {
  node.setData(
    {
      ...node.getData(),
      fetchError: false,
      errorMessage: undefined,
    },
    { overwrite: true },
  );
  hideFetchErrorIcon(node);
};
