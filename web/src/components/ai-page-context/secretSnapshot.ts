const SECRET_LABEL_RE = /password|passwd|secret|token|community|access[_\s-]?key|api[_\s-]?key|密钥|口令|凭据|snmp\s*community/i;

export const isSecretFieldLabel = (label: string): boolean => SECRET_LABEL_RE.test(label || '');

export const isSecretControl = (node: Element): boolean => {
  if (node.matches('input[type="password"], .ant-input-password, .ant-input-password-input')) return true;
  return Boolean(node.querySelector('input[type="password"], .ant-input-password'));
};

const fieldValue = (item: Element): string => {
  const inputs = Array.from(item.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea'))
    .filter((node) => node.type !== 'password' && !node.closest('.ant-input-password'))
    .map((node) => (node.value || '').trim())
    .filter(Boolean);
  const selects = Array.from(item.querySelectorAll('.ant-select-selection-item'))
    .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  return [...new Set([...selects, ...inputs])].join('、');
};

/** 可见接入事实：跳过密码框和密钥类表单项。 */
export const readVisibleFormFacts = (root?: Element | Document | null): string[] => {
  const scope = root || document;
  const items = Array.from(scope.querySelectorAll?.('.ant-form-item') || []);
  const lines: string[] = [];
  for (const item of items) {
    if (isSecretControl(item)) continue;
    const label = (item.querySelector('label')?.textContent || '').replace(/\s+/g, ' ').trim().replace(/[:：]\s*$/, '');
    if (isSecretFieldLabel(label)) continue;
    const value = fieldValue(item);
    if (!label && !value) continue;
    lines.push(value ? `${label || '字段'}: ${value}` : `${label}:`);
  }
  return lines;
};

export const snapshotContainsSecretSentinel = (text: string, sentinel: string): boolean =>
  Boolean(sentinel) && text.includes(sentinel);
