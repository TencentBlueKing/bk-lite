/**
 * 已迁移：该 API Route 属于旧的微信独立扫码登录链路。
 *
 * 自 2026-06-18 signin validation cutover 后，微信登录已收敛到
 * login-auth binding 统一流程（/auth/signin/login-auth/*），
 * 通过微信作为标准 binding provider 完成
 * start_login_auth -> callback -> poll status -> session sync。
 *
 * 本接口不再参与主登录流程，保留仅作为历史参考/兼容兜底，
 * 新需求请直接使用 login-auth validation 链路。
 *
 * 相关文档：docs/superpowers/plans/2026-06-18-signin-validation-cutover.md
 */

import {NextRequest, NextResponse} from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const code = typeof body?.code === 'string' ? body.code : '';

    if (!code) {
      return NextResponse.json({ result: false, message: 'Missing code' }, { status: 400 });
    }

    // Pass code to backend for secure verification
    // Backend handles WeChat OAuth verification and user registration
    const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/wechat_login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code }),
      cache: 'no-store',
    });

    const data = await response.json();

    if (!response.ok || !data?.result) {
      return NextResponse.json({
        result: false,
        message: data?.message || 'WeChat login failed',
        data: data,
      }, { status: response.status >= 400 ? response.status : 400 });
    }

    return NextResponse.json({
      result: true,
      data: {
        id: String(data.data.id || data.data.username || data.data.openid),
        username: data.data.username,
        token: data.data.token,
        locale: data.data.locale || 'zh',
        timezone: data.data.timezone || 'Asia/Shanghai',
        temporary_pwd: data.data.temporary_pwd || false,
        enable_otp: data.data.enable_otp || false,
        qrcode: data.data.qrcode || false,
        provider: 'wechat',
        wechatOpenId: data.data.openid,
        wechatUnionId: data.data.unionid,
      },
    });
  } catch (error) {
    console.error('wechat-popup-login error:', error);
    return NextResponse.json({
      result: false,
      message: error instanceof Error ? error.message : 'Unexpected error',
    }, { status: 500 });
  }
}
