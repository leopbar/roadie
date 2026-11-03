import { NextResponse, type NextRequest } from "next/server";

// Guarda de rota barata: sem a sessão de refresh, nem tenta renderizar o console.
// A autenticação de verdade acontece na API, a cada requisição.
export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has("roadie_refresh");
  const { pathname } = request.nextUrl;

  if (pathname === "/login") {
    return hasSession ? NextResponse.redirect(new URL("/simulador", request.url)) : NextResponse.next();
  }
  if (!hasSession) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|favicon.svg|icon.svg).*)"],
};
