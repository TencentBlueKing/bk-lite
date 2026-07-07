import fs from 'node:fs';
import path from 'node:path';

type SourceFileKey = keyof typeof sourceFiles;

const root = process.cwd();

const sourceFiles = {
  signinClient: 'src/app/(core)/auth/signin/SigninClient.tsx',
  builtinSigninContent: 'src/app/(core)/auth/signin/login-auth/BuiltinSigninContent.tsx',
  bindingPasswordCopy: 'src/app/(core)/auth/signin/login-auth/bindingPasswordCopy.ts',
  loginAuthBindingContent: 'src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx',
  useLoginAuthValidation: 'src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts',
} as const;

const requiredLocaleKeys = [
  'signin.pageTitle.login',
  'signin.pageDescription.login',
  'signin.form.username',
  'signin.form.usernamePlaceholder',
  'signin.form.password',
  'signin.form.passwordPlaceholder',
  'signin.form.signIn',
  'signin.form.signingIn',
  'signin.loginAuth.methodsTitle',
  'signin.loginAuth.bindingPassword.usernameLabel',
  'signin.loginAuth.bindingPassword.usernamePlaceholder',
  'signin.loginAuth.bindingPassword.passwordLabel',
  'signin.loginAuth.bindingPassword.passwordPlaceholder',
  'signin.loginAuth.bindingPassword.submitText',
  'signin.loginAuth.bindingPassword.loadingText',
  'signin.loginAuth.bindingContent.completingSignIn',
  'signin.loginAuth.bindingContent.startingAuthentication',
  'signin.loginAuth.bindingContent.waitingForAuthentication',
  'signin.loginAuth.bindingContent.loadErrorTitle',
  'signin.loginAuth.bindingContent.loadErrorDescription',
  'signin.loginAuth.bindingContent.retry',
  'signin.loginAuth.bindingContent.bindingTitle',
  'signin.loginAuth.bindingContent.bindingDescription',
  'signin.loginAuth.bindingContent.continueSignIn',
  'signin.loginAuth.bindingContent.waiting',
  'signin.loginAuth.bindingContent.helperMessage',
  'signin.loginAuth.validation.loadMethodsFailed',
  'signin.loginAuth.validation.timedOut',
  'signin.loginAuth.validation.cancelled',
  'signin.loginAuth.validation.failed',
  'signin.loginAuth.validation.incompletePayload',
  'signin.loginAuth.validation.syncFailed',
  'signin.loginAuth.validation.queryStatusFailed',
  'signin.loginAuth.validation.startFailed',
  'signin.loginAuth.validation.popupBlocked',
] as const;

const forbiddenHardcodedCopy: Array<{
  file: SourceFileKey;
  snippet: string;
  copy: string;
}> = [
  {
    file: 'signinClient',
    snippet: '>Sign In</h2>',
    copy: 'Sign In page title',
  },
  {
    file: 'signinClient',
    snippet: '>Enter your credentials to continue</p>',
    copy: 'Enter your credentials to continue page description',
  },
  {
    file: 'signinClient',
    snippet: 'methodsTitle="切换登录方式"',
    copy: '切换登录方式 methods title',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'usernameLabel = "Username"',
    copy: 'Username label default',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'usernamePlaceholder = "Enter your username"',
    copy: 'Enter your username placeholder default',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'passwordLabel = "Password"',
    copy: 'Password label default',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'passwordPlaceholder = "Enter your password"',
    copy: 'Enter your password placeholder default',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'submitText = "Sign In"',
    copy: 'Sign In button default',
  },
  {
    file: 'builtinSigninContent',
    snippet: 'loadingText = "Signing in..."',
    copy: 'Signing in loading default',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: '${bindingName} Username',
    copy: '{bindingName} Username binding label',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: 'Enter your ${bindingName} username',
    copy: 'Enter your {bindingName} username binding placeholder',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: '${bindingName} Password',
    copy: '{bindingName} Password binding label',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: 'Enter your ${bindingName} password',
    copy: 'Enter your {bindingName} password binding placeholder',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: 'Sign in with ${bindingName}',
    copy: 'Sign in with {bindingName} binding button',
  },
  {
    file: 'bindingPasswordCopy',
    snippet: 'Signing in with ${bindingName}...',
    copy: 'Signing in with {bindingName} binding loading text',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Completing sign-in',
    copy: 'Completing sign-in waiting title',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Starting authentication',
    copy: 'Starting authentication waiting title',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Waiting for authentication',
    copy: 'Waiting for authentication waiting title',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: '点击后将在新窗口中完成验证。若未跳转，可检查浏览器是否拦截弹窗。',
    copy: 'third-party sign-in helper message',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Unable to load login methods',
    copy: 'Unable to load login methods error title',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Please retry to load the available sign-in options.',
    copy: 'retry login methods fallback message',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: '>Retry</button>',
    copy: 'Retry button label',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: '{selectedBinding.name}登录',
    copy: '{bindingName} 登录 title',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: '使用{selectedBinding.name}账号完成登录',
    copy: '使用 {bindingName} 账号完成登录 description',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: '>Waiting...</span>',
    copy: 'Waiting loading button label',
  },
  {
    file: 'loginAuthBindingContent',
    snippet: 'Click to continue sign in',
    copy: 'Click to continue sign in button label',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Failed to load login methods. Please refresh and try again.',
    copy: 'load login methods failed validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Authentication timed out. Please try again.',
    copy: 'authentication timed out validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Authentication was cancelled. Please try again.',
    copy: 'authentication cancelled validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Authentication failed. Please try again.',
    copy: 'authentication failed validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Authentication succeeded, but the returned login payload is incomplete.',
    copy: 'incomplete login payload validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Authentication succeeded, but session synchronization failed.',
    copy: 'session synchronization failed validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Failed to query authentication status.',
    copy: 'query authentication status failed validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Unable to open the authentication page. Please allow new tabs and try again.',
    copy: 'authentication popup blocked validation error',
  },
  {
    file: 'useLoginAuthValidation',
    snippet: 'Failed to start authentication.',
    copy: 'start authentication failed validation error',
  },
];


function getLocaleValue(locale: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object' || !(segment in current)) {
      return undefined;
    }

    return (current as Record<string, unknown>)[segment];
  }, locale);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

const sourceText = Object.fromEntries(
  Object.entries(sourceFiles).map(([key, relativePath]) => [
    key,
    fs.readFileSync(path.join(root, relativePath), 'utf8'),
  ]),
) as Record<SourceFileKey, string>;

const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/locales/zh.json'), 'utf8')) as unknown;
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/locales/en.json'), 'utf8')) as unknown;
const failures: string[] = [];

for (const { file, snippet, copy } of forbiddenHardcodedCopy) {
  if (sourceText[file].includes(snippet)) {
    failures.push(`${sourceFiles[file]} still contains hardcoded user-visible copy: ${copy}`);
  }
}

for (const [localeName, locale] of [['zh', zh], ['en', en]] as const) {
  for (const key of requiredLocaleKeys) {
    if (!isNonEmptyString(getLocaleValue(locale, key))) {
      failures.push(`src/locales/${localeName}.json is missing non-empty locale key: ${key}`);
    }
  }
}

if (failures.length > 0) {
  console.error('signin i18n coverage validation failed:');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  console.error('\nMove the listed login copy behind i18n and add every required key to both zh/en locales.');
  process.exit(1);
}

console.log('signin i18n coverage validation passed');
