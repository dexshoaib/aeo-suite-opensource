import { describe, expect, it } from "vitest";
import {
  buildMetaSnippet,
  buildWellKnownUrl,
  describeVerificationError,
} from "./verification";

describe("verification helpers", () => {
  it("builds the exact meta snippet", () => {
    expect(buildMetaSnippet("tok1")).toBe(
      '<meta name="aeo-suite-verification" content="tok1">'
    );
  });

  it("builds the well-known URL on https with standard port", () => {
    expect(buildWellKnownUrl("example.com")).toBe(
      "https://example.com/.well-known/aeo-suite-verification.txt"
    );
  });

  it("maps every backend error code to copy and fails safe", () => {
    for (const code of ["no_token", "mismatch", "timeout", "network_error", "blocked", "too_large"]) {
      expect(describeVerificationError(code)).not.toBe("Verification failed.");
    }
    expect(describeVerificationError(undefined)).toBe("Verification failed.");
    expect(describeVerificationError("")).toBe("Verification failed.");
  });
});
