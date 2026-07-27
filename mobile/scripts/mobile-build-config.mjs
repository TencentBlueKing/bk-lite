export const H5_BASE_PATH = '/mobile/h5';

const BUILD_TARGETS = new Set(['h5', 'tauri']);

function requireBuildTarget(target) {
  if (!target) {
    throw new Error('须指定 Mobile 构建目标：h5 或 tauri');
  }
  if (!BUILD_TARGETS.has(target)) {
    throw new Error(`不支持的 Mobile 构建目标：${target}`);
  }
  return target;
}

function normalizeApiUrl(value) {
  if (!value) {
    throw new Error(
      'Tauri 开发或构建需要配置 NEXT_PUBLIC_API_URL，例如 https://bklite.example.com',
    );
  }

  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error('NEXT_PUBLIC_API_URL 须是绝对 HTTP(S) 地址');
  }

  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('NEXT_PUBLIC_API_URL 须是绝对 HTTP(S) 地址');
  }

  const hostname = url.hostname.replace(/^\[|\]$/g, '').toLowerCase();
  const isLoopback = hostname === 'localhost'
    || hostname === '::1'
    || hostname.startsWith('127.');
  if (url.protocol === 'http:' && !isLoopback) {
    throw new Error('NEXT_PUBLIC_API_URL 外部地址必须使用 HTTPS');
  }

  return url.toString().replace(/\/$/, '');
}

export function resolveBuildSettings({ target, env = process.env } = {}) {
  const buildTarget = requireBuildTarget(target);
  const resolvedEnv = {
    ...env,
    BK_MOBILE_BUILD_TARGET: buildTarget,
  };

  if (buildTarget === 'h5') {
    resolvedEnv.NEXT_PUBLIC_BASE_PATH = H5_BASE_PATH;
    resolvedEnv.NEXT_PUBLIC_API_URL = '';

    return {
      target: buildTarget,
      basePath: H5_BASE_PATH,
      env: resolvedEnv,
    };
  }

  const apiUrl = normalizeApiUrl(env.NEXT_PUBLIC_API_URL);
  const apiHost = new URL(apiUrl).host;
  const configuredAllowedHosts = env.TAURI_ALLOWED_HOSTS?.trim();

  resolvedEnv.NEXT_PUBLIC_BASE_PATH = '';
  resolvedEnv.NEXT_PUBLIC_API_URL = apiUrl;
  resolvedEnv.TAURI_ALLOWED_HOSTS = configuredAllowedHosts ? configuredAllowedHosts : apiHost;

  return {
    target: buildTarget,
    basePath: '',
    env: resolvedEnv,
  };
}
