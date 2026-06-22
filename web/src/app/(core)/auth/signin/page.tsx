import { getAuthOptions } from "@/constants/authOptions";
// @ts-expect-error - next-auth v4 getServerSession exists but types may not be exported correctly
import { getServerSession } from "next-auth";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import SigninClient from "./SigninClient";
import { buildThirdLoginCallbackUrl, resolveThirdLoginFlag } from "@/utils/authRedirect";
import PopupAuthBridge from "./PopupAuthBridge";

const signinErrors: Record<string | "default", string> = {
  default: "Unable to sign in.",
  signin: "Try signing in with a different account.",
  oauthsignin: "Try signing in with a different account.",
  oauthcallbackerror: "Try signing in with a different account.",
  oauthcreateaccount: "Try signing in with a different account.",
  emailcreateaccount: "Try signing in with a different account.",
  callback: "Try signing in with a different account.",
  oauthaccountnotlinked: "To confirm your identity, sign in with the same account you used originally.",
  sessionrequired: "Please sign in to access this page.",
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
  const shouldRedirectAuthenticatedUser = Boolean(session?.user?.id);

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
