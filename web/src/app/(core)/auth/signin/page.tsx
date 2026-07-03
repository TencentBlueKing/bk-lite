import { getAuthOptions } from "@/constants/authOptions";
import { getServerSession } from "next-auth";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import SigninClient from "./SigninClient";
import { buildThirdLoginCallbackUrl, resolveThirdLoginFlag } from "@/utils/authRedirect";
import PopupAuthBridge from "./PopupAuthBridge";

const signinErrors: Record<string | "default", string> = {
  default: "signin.errors.default",
  signin: "signin.errors.signin",
  oauthsignin: "signin.errors.oauthSignin",
  oauthcallbackerror: "signin.errors.oauthCallbackError",
  oauthcreateaccount: "signin.errors.oauthCreateAccount",
  emailcreateaccount: "signin.errors.emailCreateAccount",
  callback: "signin.errors.callback",
  oauthaccountnotlinked: "signin.errors.oauthAccountNotLinked",
  sessionrequired: "signin.errors.sessionRequired",
};

interface SignInPageProp {
  params?: Promise<any>;
  searchParams: Promise<{
    callbackUrl: string;
    error: string;
    third_login?: string;
    thirdLogin?: string;
    popup?: string;
    provider?: string;
  }>;
}

export default async function SigninPage({ searchParams }: SignInPageProp) {
  const authOptions = await getAuthOptions();
  const session = await getServerSession(authOptions);
  const resolvedSearchParams = await searchParams;
  const requestHeaders = await headers();
  // Derive the current origin from the incoming request so that
  // buildThirdLoginCallbackUrl can validate absolute callbackUrls correctly
  // in this server-side context (window.location is not available on the server).
  const requestHost = requestHeaders.get('x-forwarded-host') || requestHeaders.get('host') || '';
  const requestProto = requestHeaders.get('x-forwarded-proto') || 'https';
  const requestOrigin = requestHost ? `${requestProto}://${requestHost}` : '';
  const thirdLoginFlag = resolveThirdLoginFlag(
    resolvedSearchParams.thirdLogin,
    resolvedSearchParams.third_login,
  );
  const isPopupMode = resolvedSearchParams.popup === 'true' || resolvedSearchParams.popup === '1';
  const shouldRedirectAuthenticatedUser = Boolean(
    session
    && session.user
    && session.user.id
    && (isPopupMode || !thirdLoginFlag || resolvedSearchParams.provider === 'wechat')
  );

  if (shouldRedirectAuthenticatedUser) {
    if (isPopupMode) {
      return (
        <PopupAuthBridge
          callbackUrl={resolvedSearchParams.callbackUrl}
          thirdLogin={thirdLoginFlag}
          user={{
            id: session.user.id,
            username: session.user.username,
            token: session.user.token,
            locale: session.user.locale,
            temporary_pwd: session.user.temporary_pwd,
            enable_otp: session.user.enable_otp,
            qrcode: session.user.qrcode,
          }}
        />
      );
    }

    redirect(
      buildThirdLoginCallbackUrl(
        resolvedSearchParams.callbackUrl,
        session.user.token,
        thirdLoginFlag,
        requestOrigin,
      ),
    );
  }
  return <SigninClient searchParams={resolvedSearchParams} signinErrors={signinErrors} />;
}
