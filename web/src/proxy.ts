import { NextResponse, type NextRequest } from "next/server";

/* Optimistic auth gate: app routes need the Supabase session cookie the API
   sets on login. Real authorization happens in the API on every request. */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("sb_access") || request.cookies.has("sb_refresh");
  if (!hasSession && pathname !== "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (hasSession && pathname === "/login" && !request.nextUrl.searchParams.has("force")) {
    const url = request.nextUrl.clone();
    url.pathname = url.searchParams.get("next") ?? "/";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|pub|_next|icon.svg|favicon.ico|brand).*)"],
};
