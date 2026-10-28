/**
 * Inloggen via OIDC (Keycloak) met Authorization Code + PKCE.
 * Met VITE_AUTH_MODE=none (standaard) is er geen login en stuurt de app geen token mee.
 * Wie niet is ingelogd, ziet eerst de landingspagina; de knop daar start de login.
 */
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts';

export const authEnabled = import.meta.env.VITE_AUTH_MODE === 'oidc';

let manager: UserManager | null = null;
let user: User | null = null;

function getManager(): UserManager {
  manager ??= new UserManager({
    authority: import.meta.env.VITE_OIDC_AUTHORITY ?? 'http://localhost:8180/realms/finkennis',
    client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? 'finkennis-frontend',
    redirect_uri: `${window.location.origin}/`,
    post_logout_redirect_uri: `${window.location.origin}/`,
    response_type: 'code',
    scope: 'openid profile email',
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
  return manager;
}

/** Geeft true als er een geldige sessie is, ook direct na de terugkeer van Keycloak. */
export async function initAuth(): Promise<boolean> {
  if (!authEnabled) return true;
  const m = getManager();
  m.events.addUserLoaded((u) => {
    user = u;
  });
  const params = new URLSearchParams(window.location.search);
  if (params.has('code') && params.has('state')) {
    try {
      user = await m.signinRedirectCallback();
    } catch (e) {
      // Verlopen of dubbel gebruikte code: gewoon opnieuw laten inloggen.
      console.warn('Inloggen afronden mislukt', e);
    }
    window.history.replaceState({}, document.title, window.location.pathname);
  } else {
    user = await m.getUser();
  }
  if (user?.expired) {
    user = await m.signinSilent().catch(() => null);
  }
  return !!user && !user.expired;
}

export async function login(): Promise<void> {
  await getManager().signinRedirect();
}

export async function accessToken(): Promise<string | null> {
  if (!authEnabled) return null;
  if (user?.expired) user = await getManager().signinSilent();
  return user?.access_token ?? null;
}

export function gebruikersnaam(): string | null {
  return (user?.profile.name as string | undefined) ?? user?.profile.preferred_username ?? null;
}

export async function logout(): Promise<void> {
  await getManager().signoutRedirect();
}
