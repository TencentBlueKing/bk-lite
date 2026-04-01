import { NextRequest, NextResponse } from 'next/server';

async function getWeChatSettings() {
  const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/get_wechat_settings/`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Pragma: 'no-cache',
    },
    cache: 'no-store',
  });

  const responseData = await response.json();

  if (!response.ok || !responseData?.result || !responseData?.data?.app_id || !responseData?.data?.app_secret) {
    throw new Error(responseData?.message || 'Failed to fetch WeChat settings');
  }

  return responseData.data;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const code = typeof body?.code === 'string' ? body.code : '';

    if (!code) {
      return NextResponse.json({ result: false, message: 'Missing code' }, { status: 400 });
    }

    const wechatSettings = await getWeChatSettings();

    const tokenUrl = new URL('https://api.weixin.qq.com/sns/oauth2/access_token');
    tokenUrl.searchParams.set('appid', wechatSettings.app_id);
    tokenUrl.searchParams.set('secret', wechatSettings.app_secret);
    tokenUrl.searchParams.set('code', code);
    tokenUrl.searchParams.set('grant_type', 'authorization_code');

    const tokenResponse = await fetch(tokenUrl.toString(), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      cache: 'no-store',
    });

    const tokenData = await tokenResponse.json();

    if (!tokenResponse.ok || tokenData?.errcode || !tokenData?.access_token || !tokenData?.openid) {
      return NextResponse.json({
        result: false,
        message: tokenData?.errmsg || 'Failed to exchange WeChat code',
        data: tokenData,
      }, { status: 400 });
    }

    const userinfoUrl = new URL('https://api.weixin.qq.com/sns/userinfo');
    userinfoUrl.searchParams.set('access_token', tokenData.access_token);
    userinfoUrl.searchParams.set('openid', tokenData.openid);
    userinfoUrl.searchParams.set('lang', 'zh_CN');

    const userinfoResponse = await fetch(userinfoUrl.toString(), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      cache: 'no-store',
    });

    const userinfoData = await userinfoResponse.json();

    if (!userinfoResponse.ok || userinfoData?.errcode || !userinfoData?.openid) {
      return NextResponse.json({
        result: false,
        message: userinfoData?.errmsg || 'Failed to fetch WeChat user info',
        data: userinfoData,
      }, { status: 400 });
    }

    const registerResponse = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/wechat_user_register/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: userinfoData.openid,
        nick_name: userinfoData.nickname || userinfoData.openid,
      }),
      cache: 'no-store',
    });

    const registerData = await registerResponse.json();

    if (!registerResponse.ok || !registerData?.result || !registerData?.data) {
      return NextResponse.json({
        result: false,
        message: registerData?.message || 'Failed to register WeChat user',
        data: registerData,
      }, { status: 400 });
    }

    return NextResponse.json({
      result: true,
      data: {
        id: String(registerData.data.id || registerData.data.username || userinfoData.openid),
        username: registerData.data.username,
        token: registerData.data.token,
        locale: registerData.data.locale || 'zh',
        temporary_pwd: registerData.data.temporary_pwd || false,
        enable_otp: registerData.data.enable_otp || false,
        qrcode: registerData.data.qrcode || false,
        provider: 'wechat',
        wechatOpenId: userinfoData.openid,
        wechatUnionId: userinfoData.unionid,
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