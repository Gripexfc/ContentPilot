import { describe, expect, it } from "vitest";
import { createDefaultProfile, joinList, resolvePlatformProfile, splitList } from "./profile";

describe("profile list helpers", () => {
  it("normalizes Chinese and ASCII separators", () => {
    expect(splitList("工程实践，内容产品, 真实案例\n")).toEqual(["工程实践", "内容产品", "真实案例"]);
    expect(joinList(["工程实践", "内容产品"])).toBe("工程实践、内容产品");
  });

  it("inherits shared defaults and keeps platform overrides local", () => {
    const profile = createDefaultProfile();
    const shared = resolvePlatformProfile(profile, "wechat");

    expect(shared.positioning).toBe(profile.content_defaults?.positioning);
    expect(shared.format_preferences).toEqual(profile.content_defaults?.format_preferences);
    expect(shared.tone).toBe(profile.voice.tone);

    profile.platforms.wechat = {
      ...profile.platforms.wechat,
      positioning: "围绕公众号读者的决策场景",
      tone: "克制、具体",
    };

    const overridden = resolvePlatformProfile(profile, "wechat");
    expect(overridden.positioning).toBe("围绕公众号读者的决策场景");
    expect(overridden.tone).toBe("克制、具体");
    expect(overridden.format_preferences).toEqual(profile.content_defaults?.format_preferences);
  });
});
