import type {OAuthConfig, OAuthUserConfig} from "next-auth/providers/oauth";

export interface WechatProfile {
  openid: string;
  nickname?: string;
  sex?: string;
  province?: string;
  city?: string;
  country?: string;
  headimgurl?: string;
  privilege?: string[];
  unionid?: string;
  access_token?: string;
  // Extended fields from backend response
  id?: number;
  username?: string;
  token?: string;
  locale?: string;
  timezone?: string;
}

export default function WeChatProvider<P extends WechatProfile>(
  options: OAuthUserConfig<P> & { redirectUri: string }
): OAuthConfig<P> {
  console.log("[WeChat OAuth] Initializing WeChat Provider with options:", {
    clientId: options.clientId ? "Set" : "Not set",
    redirectUri: options.redirectUri,
  });

  return {
    id: "wechat",
    name: "WeChat",
    type: "oauth",
    version: "2.0",
    wellKnown: undefined,
    authorization: {
      url: "https://open.weixin.qq.com/connect/qrconnect",
      params: {
        appid: options.clientId,
        response_type: "code",
        scope: "snsapi_login",
        redirect_uri: options.redirectUri
      }
    },
    token: {
      url: "https://api.weixin.qq.com/sns/oauth2/access_token",
      async request({ params }) {
        console.log("[WeChat OAuth] Token request - passing code to backend");
        
        // Instead of calling WeChat API directly, pass code to backend
        // Backend handles WeChat OAuth verification securely
        const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/wechat_login/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ code: params.code }),
        });

        const data = await response.json();
        console.log("[WeChat OAuth] Backend response:", {
          result: data.result,
          hasData: !!data.data,
          message: data.message,
        });

        if (!data.result || !data.data) {
          throw new Error(`WeChat login failed: ${data.message || 'Unknown error'}`);
        }

        // Return tokens in next-auth expected format
        // Store backend response data in tokens for use in profile()
        return {
          tokens: {
            access_token: data.data.token, // Use backend JWT as access_token
            openid: data.data.openid,
            unionid: data.data.unionid,
            // Store full backend response for profile()
            backend_data: data.data,
          }
        };
      }
    },
    userinfo: {
      url: "https://api.weixin.qq.com/sns/userinfo",
      async request({ tokens }) {
        console.log("[WeChat OAuth] Userinfo - using backend data");
        
        // We already have all user info from the backend response
        // No need to call WeChat API again
        const backendData = (tokens as any).backend_data;
        
        return {
          openid: backendData.openid,
          nickname: backendData.display_name || backendData.username,
          unionid: backendData.unionid,
          // Include backend data for profile()
          ...backendData,
        };
      }
    },
    async profile(profile) {
      console.log("[WeChat OAuth] Processing profile:", {
        openid: profile.openid || "Not received",
        username: profile.username || "Not received",
        id: profile.id || "Not received",
      });

      // User is already registered by backend's wechat_login endpoint
      // Just return the profile data
      return {
        id: String(profile.id || profile.username || profile.openid),
        name: profile.username || profile.nickname || profile.openid,
        username: profile.username,
        image: profile.headimgurl,
        email: null,
        token: profile.token,
        locale: profile.locale || 'zh',
        timezone: profile.timezone || 'Asia/Shanghai',
        wechatOpenId: profile.openid,
        wechatUnionId: profile.unionid,
      };
    },
    clientId: options.clientId || "",
    clientSecret: options.clientSecret || ""
  };
}
