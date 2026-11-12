export const actionOf = (nodeId: string) => (nodeId === 'approve' ? 'approve' : 'submit');

export const actionLabel = (nodeId: string) => (nodeId === 'approve' ? '通过' : '提交');
