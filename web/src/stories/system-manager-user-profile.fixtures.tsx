import MarkdownRenderer from '@/components/markdown';

export const systemManagerStorybookUserInfo = {
  username: 'storybook',
  display_name: 'Storybook User',
  email: 'storybook@example.com',
  timezone: 'Asia/Shanghai',
  locale: 'zh-hans',
};

export const systemManagerStorybookPasswordPolicy = {
  pwd_set_min_length: '10',
  pwd_set_max_length: '20',
  pwd_set_required_char_types: ['uppercase', 'lowercase', 'digit'],
};

export const systemManagerVersionContentMap: Record<string, string> = {
  'v2.8.0': `
# v2.8.0

- Unified shared modal and drawer contracts
- Added Storybook governance for user profile surfaces
- Refined account self-service workflows
`,
  'v2.7.4': `
# v2.7.4

- Improved audit filtering and role-transfer polish
- Refined password-policy guidance
`,
};

export const renderSystemManagerVersionContent = (versionFile: string) => (
  <MarkdownRenderer content={systemManagerVersionContentMap[versionFile] || ''} />
);
