import type { Platform } from "../api";

export const platformLabel = (platform: Platform): string =>
  platform === "wechat" ? "公众号" : platform === "xiaohongshu" ? "小红书" : "抖音";

export const contentPreview = (value: Record<string, any>): string => {
  const candidates = [value.title, value.summary, value.cover_copy, value.hook_3s, value.body, value.voiceover];
  const first = candidates.find((item) => typeof item === "string" && item.trim());
  return typeof first === "string" ? first : "已生成结构化内容，可展开查看。";
};
