import { describe, expect, it } from "vitest";
import { isDraftDirty, previewDocument } from "../DraftCenter";

const blank = { title: "", digest: "", author: "", content_html: "<p>从这里开始写公众号正文。</p>" };

describe("draft center safeguards", () => {
  it("blocks navigation and submit until a draft form is saved", () => {
    const saved = { title: "标题", digest: "摘要", author: "作者", content_html: "<p>旧正文</p>" };
    expect(isDraftDirty({ ...saved, content_html: "<p>新正文</p>" }, saved, true)).toBe(true);
    expect(isDraftDirty(saved, saved, true)).toBe(false);
    expect(isDraftDirty(blank, null, false)).toBe(false);
  });

  it("builds an isolated preview document without executable script permission", () => {
    const document = previewDocument("<p>正文</p><script>window.evil=true</script>");
    expect(document).toContain("default-src 'none'");
    expect(document).toContain("form-action 'none'");
    expect(document).toContain("<script>");
  });
});
