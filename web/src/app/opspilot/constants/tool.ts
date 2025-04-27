import { useTranslation } from '@/utils/i18n';
export const getFormFields = (t: ReturnType<typeof useTranslation>['t'], groups: any) => {
  return [
    {
      name: 'name',
      type: 'input',
      label: t('tool.name'),
      placeholder: `${t('common.inputMsg')}${t('tool.name')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.name')}` }],
    },
    {
      name: 'tags',
      type: 'select',
      label: t('tool.label'),
      placeholder: `${t('common.selectMsg')}${t('tool.label')}`,
      options: [
        {
          value: 'search',
          label: `${t('tool.search')} ${t('tool.title')}`
        },
        {
          value: 'general',
          label: `${t('tool.general')} ${t('tool.title')}`
        },
        {
          value: 'maintenance',
          label: `${t('tool.maintenance')} ${t('tool.title')}`
        },
        {
          value: 'media',
          label: `${t('tool.media')} ${t('tool.title')}`
        },
        {
          value: 'collaboration',
          label: `${t('tool.collaboration')} ${t('tool.title')}`
        },
        {
          value: 'other',
          label: `${t('tool.other')} ${t('tool.title')}`
        }
      ],
      mode: 'multiple',
      rules: [{ required: true, message: `${t('common.selectMsg')}${t('tool.label')}` }],
    },
    {
      name: 'url',
      type: 'input',
      label: t('tool.mcpUrl'),
      placeholder: `${t('common.inputMsg')}${t('tool.mcpUrl')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.mcpUrl')}` }],
    },
    {
      name: 'team',
      type: 'select',
      label: t('common.group'),
      placeholder: `${t('common.selectMsg')}${t('common.group')}`,
      options: groups.map((group: any) => ({ value: group.id, label: group.name })),
      mode: 'multiple',
      rules: [{ required: true, message: `${t('common.selectMsg')}${t('common.group')}` }],
    },
    {
      name: 'description',
      type: 'textarea',
      label: t('tool.description'),
      rows: 4,
      placeholder: `${t('common.inputMsg')}${t('tool.description')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.description')}` }],
    },
  ];
};
