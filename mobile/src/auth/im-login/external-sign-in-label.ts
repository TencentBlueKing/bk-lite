const NAME_ALREADY_HAS_LOGIN = /登录|登陆|sign[\s-]?in|log\s*in/i;

export function externalSignInMessageId(name: string): 'login.externalUse' | 'login.externalSignIn' {
  return NAME_ALREADY_HAS_LOGIN.test(name.trim()) ? 'login.externalUse' : 'login.externalSignIn';
}
