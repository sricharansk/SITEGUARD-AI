// Next.js 16 proxy (formerly middleware): send visitors without a session cookie to /login. This is only an
// optimistic redirect; the API validates the token on every call and answers 401 when it is missing or expired.
import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/server/session";

export function proxy(request: NextRequest) {
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  const { pathname, search } = request.nextUrl;

  if (pathname === "/login") {
    return NextResponse.next();
  }
  if (!hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Route handlers under /api answer 401 themselves; static assets need no session.
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)"],
};
