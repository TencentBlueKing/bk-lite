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
