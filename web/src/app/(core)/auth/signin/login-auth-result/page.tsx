import type { LoginAuthResultPageSearchParams, LoginAuthResultStatus } from "../login-auth/types";

interface LoginAuthResultPageProps {
  searchParams: Promise<LoginAuthResultPageSearchParams>;
}

function normalizeStatus(status?: string): LoginAuthResultStatus {
  if (status === "success" || status === "cancelled" || status === "expired") {
    return status;
  }
  return "failed";
}

function getResultTitle(status: LoginAuthResultStatus) {
  if (status === "success") {
    return "认证完成";
  }
  if (status === "cancelled") {
    return "认证已取消";
  }
  if (status === "expired") {
    return "认证已过期";
  }
  return "认证失败";
}

export default async function LoginAuthResultPage({ searchParams }: LoginAuthResultPageProps) {
  const resolvedSearchParams = await searchParams;
  const status = normalizeStatus(resolvedSearchParams.status);
  const message = resolvedSearchParams.message || "请关闭当前页面并返回原登录页。";
  const isSuccess = status === "success";

  return (
    <div className="fixed inset-0 flex items-center justify-center px-6 py-8 text-center text-[#1f2329]">
      <div className="w-full max-w-[420px] rounded-[28px] bg-white px-8 py-9 shadow-[0_18px_44px_rgba(15,35,95,0.10)]">
        <div
          className={`mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full text-2xl font-bold text-white ${
            isSuccess ? "bg-[#14a568]" : "bg-[#f04438]"
          }`}
        >
          {isSuccess ? "✓" : "!"}
        </div>
        <h1 className="mb-3 text-[32px] font-semibold leading-none text-[#1f2329]">{getResultTitle(status)}</h1>
        <p className="m-0 whitespace-pre-wrap text-[15px] leading-7 text-[#4e5969]">{message}</p>
      </div>
    </div>
  );
}
