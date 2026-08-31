/**
 * Google Analytics, only if somebody configured it.
 *
 * `VITE_GA_ID` is empty by default, and with it empty nothing is fetched and no
 * cookie is set — which is what lets `/privacy` say the site stores nothing on
 * your device. Both read this same constant, so the page cannot claim one thing
 * while the app does another.
 *
 * Vite inlines `import.meta.env` at build time, so an unset id leaves the
 * loader below unreachable in the bundle rather than merely unrun.
 */

export const GA_ID = (import.meta.env.VITE_GA_ID ?? "").trim();

export function startAnalytics(): void {
  if (!GA_ID || typeof document === "undefined") return;

  const tag = document.createElement("script");
  tag.async = true;
  tag.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}`;
  document.head.appendChild(tag);

  // gtag reads the same array it later replaces, so pushing before the script
  // lands is the documented way to configure it.
  const w = window as unknown as { dataLayer?: unknown[] };
  w.dataLayer = w.dataLayer || [];
  const gtag = (...args: unknown[]) => w.dataLayer!.push(args);
  gtag("js", new Date());
  gtag("config", GA_ID);
}
