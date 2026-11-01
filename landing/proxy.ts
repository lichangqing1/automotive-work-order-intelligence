import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(
    "x-page-language",
    request.nextUrl.pathname === "/zh" || request.nextUrl.pathname.startsWith("/zh/")
      ? "zh-CN"
      : "en",
  );

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/", "/en/:path*", "/zh/:path*", "/evidence"],
};
