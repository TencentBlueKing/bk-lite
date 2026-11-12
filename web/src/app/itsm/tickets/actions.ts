export const actionOf = (nodeType: string) => (nodeType === 'approval' ? 'approve' : 'submit');

export const actionLabel = (nodeType: string) => (nodeType === 'approval' ? '通过' : '提交');
