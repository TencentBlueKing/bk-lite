import type { ScriptVariable } from '@/components/script-editor';

const JOB_BUILTIN_SCRIPT_VARIABLE_NAMES = [
  ['BK_JOB_USER', 'job.builtinVarUser'],
  ['BK_JOB_USER_NAME', 'job.builtinVarUserName'],
  ['BK_JOB_ID', 'job.builtinVarJobId'],
] as const;

type Translate = (id: string) => string;

export const buildJobBuiltinScriptVariables = (t: Translate): ScriptVariable[] => (
  JOB_BUILTIN_SCRIPT_VARIABLE_NAMES.map(([name, descriptionId]) => ({
    key: name,
    description: t(descriptionId),
    token: {
      shell: `$${name}`,
      powershell: `$${name}`,
      python: name,
      bat: `%${name}%`,
    },
  }))
);
