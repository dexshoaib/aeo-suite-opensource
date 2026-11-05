/**
 * Site ownership verification helpers (SPEC-1.2).
 * Pure functions, unit-tested like lib/org.ts.
 */

export const META_NAME = "aeo-suite-verification";
export const WELL_KNOWN_PATH = "/.well-known/aeo-suite-verification.txt";

export function buildMetaSnippet(token: string): string {
  return `<meta name="${META_NAME}" content="${token}">`;
}

export function buildWellKnownUrl(domain: string): string {
  return `https://${domain}${WELL_KNOWN_PATH}`;
}

export function describeVerificationError(code?: string | null): string {
  switch (code) {
    case "no_token":
      return "The token was not found on the site. Publish the snippet and try again.";
    case "mismatch":
      return "A different token was found on the site. Republish the current snippet.";
    case "timeout":
      return "The site did not respond in time. Try again shortly.";
    case "network_error":
      return "The site could not be reached. Check that it is online and publicly reachable.";
    case "blocked":
      return "The site address failed our safety checks. Contact support if this persists.";
    case "too_large":
      return "The site response was too large to scan.";
    default:
      return "Verification failed.";
  }
}
