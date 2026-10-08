from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from creatoros.config import Settings
from creatoros.time_utils import utc_iso


HOME = "https://mp.weixin.qq.com/"
TOKEN_RE = re.compile(r"[?&]token=(\d+)")


class WeChatAdapterError(RuntimeError):
    code = "wechat_adapter_error"


class WeChatDependencyMissing(WeChatAdapterError):
    code = "wechat_playwright_missing"


class WeChatRemoteError(WeChatAdapterError):
    code = "wechat_remote_error"


class WeChatBrowserAdapter:
    """Opt-in adapter for an administrator's WeChat Official Account session.

    The default CreatorOS mode remains ``mock``. Browser mode uses a persistent
    Playwright profile under the configured local data directory; it never puts
    cookies, app secrets, or QR contents into the database or API responses.
    """

    def __init__(self, settings: Settings | None):
        if settings is None:
            raise WeChatAdapterError("真实公众号适配器缺少运行配置")
        self.settings = settings
        self.profile_dir = settings.wechat_profile_dir
        self.status_file = settings.data_dir / "wechat-login.json"
        self.qr_file = settings.data_dir / "wechat-login.png"
        self._login_thread: threading.Thread | None = None

    @staticmethod
    def _token(url: str) -> str:
        match = TOKEN_RE.search(url or "")
        return match.group(1) if match else ""

    @staticmethod
    def _playwright():
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise WeChatDependencyMissing("真实公众号适配器需要安装 Playwright 可选依赖") from exc
        return sync_playwright

    def preflight(self) -> None:
        self._playwright()
        self.settings.ensure_dirs()
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def _context(self, playwright: Any):
        return playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            headless=False,
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

    def _write_status(self, state: str, message: str, **extra: str) -> dict[str, str]:
        self.settings.ensure_dirs()
        payload: dict[str, str] = {"state": state, "message": message,
                                   "updated_at": utc_iso(datetime.now(timezone.utc)) or ""}
        payload.update(extra)
        self.status_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _read_status(self) -> dict[str, str]:
        if not self.status_file.exists():
            return {"state": "idle", "message": "尚未开始公众号登录"}
        try:
            return json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"state": "error", "message": "登录状态文件不可读取"}

    def start_or_check_login(self) -> dict[str, str]:
        self.preflight()
        current = self._read_status()
        if current.get("state") in {"starting", "qr_ready", "connecting"} and self._login_thread and self._login_thread.is_alive():
            return current
        if current.get("state") == "success":
            account = self.whoami()
            if account.get("logged_in"):
                return {**current, "state": "success", "message": "公众号会话仍然有效"}
        self._write_status("starting", "正在打开公众号登录页面")
        self._login_thread = threading.Thread(target=self._login_worker, daemon=True)
        self._login_thread.start()
        return self._read_status()

    def _login_worker(self) -> None:  # pragma: no cover - requires a real browser and QR scan
        try:
            sync_playwright = self._playwright()
            with sync_playwright() as playwright:
                context = self._context(playwright)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(HOME, wait_until="commit", timeout=60_000)
                    page.wait_for_timeout(1_500)
                    if self._token(page.url):
                        self._write_status("success", "公众号会话仍然有效")
                        return
                    selector = "img[src*='qrcode'], img.login__type__container__scan__qrcode"
                    qr = page.query_selector(selector)
                    if qr:
                        qr.screenshot(path=str(self.qr_file))
                        self._write_status("qr_ready", "请使用公众号管理员微信扫码", qr_path=str(self.qr_file))
                    else:
                        self._write_status("qr_ready", "登录页面已打开，请扫码")
                    deadline = time.time() + 240
                    while time.time() < deadline:
                        page.wait_for_timeout(2_000)
                        if self._token(page.url):
                            self._write_status("success", "公众号登录成功")
                            return
                    self._write_status("expired", "二维码已超时，请重新扫码")
                finally:
                    context.close()
        except Exception as exc:
            self._write_status("error", f"登录失败：{type(exc).__name__}")

    def whoami(self) -> dict[str, Any]:
        self.preflight()
        sync_playwright = self._playwright()
        try:
            with sync_playwright() as playwright:
                context = self._context(playwright)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(HOME, wait_until="commit", timeout=60_000)
                    page.wait_for_timeout(1_000)
                    logged_in = bool(self._token(page.url))
                    return {"logged_in": logged_in,
                            "message": "公众号会话有效" if logged_in else "尚未连接公众号"}
                finally:
                    context.close()
        except Exception as exc:  # pragma: no cover - browser/runtime dependent
            return {"logged_in": False, "message": f"无法检查公众号会话：{type(exc).__name__}"}

    def _require_page(self, playwright: Any):
        context = self._context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(HOME, wait_until="commit", timeout=60_000)
        page.wait_for_timeout(1_000)
        token = self._token(page.url)
        if not token:
            context.close()
            raise WeChatRemoteError("公众号会话已失效，请重新扫码登录")
        return context, page, token

    def _editor_context(self, page: Any, token: str) -> dict[str, str]:
        url = f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token={token}&lang=zh_CN"
        response = page.request.get(url, timeout=30_000)
        source = response.text()

        def grab(name: str) -> str:
            found = re.search(rf"{name}[\"']?\s*[:=]\s*[\"']?([\w%.-]+)", source)
            return found.group(1) if found else ""

        return {"ticket": grab("ticket"), "user_name": grab("user_name")}

    def upload_cover(self, page: Any, token: str, cover_path: Path) -> str:
        editor = self._editor_context(page, token)
        if not editor["ticket"] or not editor["user_name"]:
            raise WeChatRemoteError("未读取到公众号编辑器会话")
        timestamp = int(time.time() * 1000)
        mime = mimetypes.guess_type(cover_path.name)[0] or "image/jpeg"
        endpoint = f"https://mp.weixin.qq.com/cgi-bin/filetransfer?action=upload_material&f=json&scene=8&writetype=doublewrite&groupid=1&ticket_id={editor['user_name']}&ticket={editor['ticket']}&svr_time={timestamp}&token={token}&lang=zh_CN"
        response = page.request.post(endpoint, multipart={"file": {"name": cover_path.name, "mimeType": mime, "buffer": cover_path.read_bytes()}}, headers={"Referer": page.url})
        payload = response.json()
        content = payload.get("content")
        media_id = payload.get("media_id") or (content if isinstance(content, str) else content.get("media_id") if isinstance(content, dict) else "")
        if not media_id:
            raise WeChatRemoteError("公众号封面上传失败")
        return str(media_id)

    def _read_back_draft(self, page: Any, token: str, remote_id: str) -> dict[str, Any]:
        """Read the draft list after create and retain only non-sensitive evidence."""
        url = f"https://mp.weixin.qq.com/cgi-bin/appmsg?begin=0&count=20&token={token}&lang=zh_CN"
        response = page.request.get(url, timeout=30_000)
        if not response.ok:
            raise WeChatRemoteError("公众号草稿已返回成功，但回读草稿列表失败")
        body = response.text()
        return {
            "status": response.status,
            "contains_remote_id": bool(remote_id and remote_id in body),
            "read_back_at": utc_iso(datetime.now(timezone.utc)),
        }

    def publish_draft(self, html: str, cover_path: Path, title: str, digest: str, author: str) -> dict[str, Any]:
        if not cover_path.is_file():
            raise WeChatRemoteError("提交公众号草稿前需要有效的封面文件")
        sync_playwright = self._playwright()
        try:
            with sync_playwright() as playwright:
                context, page, token = self._require_page(playwright)
                try:
                    thumb = self.upload_cover(page, token, cover_path)
                    endpoint = f"https://mp.weixin.qq.com/cgi-bin/operate_appmsg?t=ajax-response&sub=create&type=10&token={token}&lang=zh_CN&f=json&ajax=1"
                    form = {
                        "token": token, "lang": "zh_CN", "f": "json", "ajax": "1",
                        "random": str(time.time())[-6:], "AppMsgId": "", "count": "1",
                        "data_seq": "0", "operate_from": "Chrome", "isnew": "1", "articlenum": "1",
                        "title0": title[:64], "author0": author[:32], "digest0": digest[:120],
                        "content0": html, "sourceurl0": "", "show_cover_pic0": "0",
                        "thumb_media_id0": thumb, "shortvideofileid0": "", "copyright_type0": "0",
                        "fileid0": "", "need_open_comment0": "0", "only_fans_can_comment0": "0",
                        "can_reward0": "0",
                    }
                    payload = page.request.post(endpoint, form=form, headers={"Referer": page.url}).json()
                    ret = payload.get("ret", payload.get("base_resp", {}).get("ret", -1))
                    if str(ret) != "0":
                        raise WeChatRemoteError("公众号草稿提交失败")
                    remote_id = str(payload.get("appMsgId", ""))
                    receipt = {"adapter": "wechat_browser", "remote_id": remote_id,
                               "cover_media_id": thumb, "response": payload,
                               "read_back": self._read_back_draft(page, token, remote_id)}
                    return receipt
                finally:
                    context.close()
        except WeChatAdapterError:
            raise
        except Exception as exc:  # pragma: no cover - browser/runtime dependent
            raise WeChatRemoteError(f"公众号草稿提交失败：{type(exc).__name__}") from exc

    def fetch_stats(self) -> dict[str, Any]:
        sync_playwright = self._playwright()
        try:
            with sync_playwright() as playwright:
                context, page, token = self._require_page(playwright)
                captured: dict[str, str] = {}

                def capture(response: Any) -> None:
                    url = response.url
                    if "appmsgpublish" in url and "publish" not in captured:
                        captured["publish"] = response.text()
                    elif "get_article_stat_tendency" in url and "tendency" not in captured:
                        captured["tendency"] = response.text()

                page.on("response", capture)
                try:
                    page.goto(f"https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token={token}&lang=zh_CN", wait_until="commit", timeout=60_000)
                    page.wait_for_timeout(4_000)
                    try:
                        page.goto(f"https://mp.weixin.qq.com/misc/appmsganalysis?action=report&type=daily_v2&token={token}&lang=zh_CN", wait_until="commit", timeout=60_000)
                        page.wait_for_timeout(4_000)
                    except Exception:
                        pass
                    return self._parse_stats(captured)
                finally:
                    context.close()
        except WeChatAdapterError:
            raise
        except Exception as exc:  # pragma: no cover - browser/runtime dependent
            raise WeChatRemoteError(f"公众号数据读取失败：{type(exc).__name__}") from exc

    @staticmethod
    def _parse_stats(captured: dict[str, str]) -> dict[str, Any]:
        notes: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        try:
            payload = json.loads(captured.get("publish", "{}"))
            page = payload.get("publish_page", {})
            if isinstance(page, str):
                page = json.loads(page)
            for item in page.get("publish_list", []):
                info = item.get("publish_info", {})
                if isinstance(info, str):
                    info = json.loads(info)
                for article in info.get("appmsgex") or info.get("appmsg_info") or []:
                    notes.append({"title": article.get("title", ""), "url": article.get("link") or article.get("content_url", ""),
                                  "cover": article.get("cover", ""), "reads": article.get("read_num"), "likes": article.get("like_num")})
            metrics.extend([{"label": "已发表", "value": int(page.get("publish_count", 0) or 0)},
                            {"label": "群发次数", "value": int(page.get("masssend_count", 0) or 0)}])
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        try:
            payload = json.loads(captured.get("tendency", "{}"))
            values = (payload.get("all_article_stat_tendency") or {}).get("list") or []
            metrics.extend([{"label": "近期开篇阅读", "value": sum(int(item.get("read_uv", 0) or 0) for item in values)},
                            {"label": "近期开篇分享", "value": sum(int(item.get("share_uv", 0) or 0) for item in values)}])
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return {"platform": "wechat-oa", "source": "wechat_browser", "fetched_at": utc_iso(datetime.now(timezone.utc)),
                "posts": len(notes), "notes": notes[:20], "metrics": metrics,
                "limitations": ["读取的是当前公众号后台可见数据；缺失字段保留为空，不推断为零。"]}
