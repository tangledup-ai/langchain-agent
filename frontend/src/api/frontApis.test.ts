import { describe, expect, it } from "vitest";

import { joinApiUrl } from "./frontApis";

describe("joinApiUrl", () => {
  it("keeps same-origin paths when base url is slash", () => {
    expect(joinApiUrl("/", "/v1/pipelines")).toBe("/v1/pipelines");
  });

  it("joins absolute host and trims trailing slash", () => {
    expect(joinApiUrl("http://127.0.0.1:8500/", "/v1/pipelines")).toBe(
      "http://127.0.0.1:8500/v1/pipelines"
    );
  });

  it("accepts path without leading slash", () => {
    expect(joinApiUrl("http://127.0.0.1:8500", "v1/pipelines")).toBe(
      "http://127.0.0.1:8500/v1/pipelines"
    );
  });
});

