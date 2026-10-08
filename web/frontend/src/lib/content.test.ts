import { describe, expect, it } from "vitest";
import { contentPreview, platformLabel } from "./content";

describe("content helpers", () => {
  it("keeps platform names and previews structured drafts", () => {
    expect(platformLabel("wechat")).toBe("公众号");
    expect(platformLabel("xiaohongshu")).toBe("小红书");
    expect(contentPreview({ summary: "先分事实和判断" })).toBe("先分事实和判断");
  });
});
