import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ breaks: true, gfm: true });

function encodedPath(path: string): string {
  return path.split('/').map((part) => encodeURIComponent(part)).join('/');
}

/**
 * Agent 可能返回 outputs/ 相对链接，或把本机绝对路径放进 Markdown。
 * 浏览器不能直接打开这些路径，统一改成 随波逐流 的受控预览接口。
 */
function localFileHref(href: string): string | null {
  let value = href.trim();
  if (!value || /^(https?:|mailto:|#|data:|javascript:)/i.test(value)) return null;

  if (/^file:/i.test(value)) {
    try { value = decodeURIComponent(new URL(value).pathname); }
    catch { return null; }
  } else {
    try { value = decodeURIComponent(value); } catch { /* keep original */ }
  }

  const outputMarker = value.match(/(?:^|\/)outputs\/(.+)$/);
  if (outputMarker) return `/api/media/${encodedPath(outputMarker[1])}`;

  // 允许模型直接引用项目根下的最终平台交付文件。
  const projectMarker = value.match(/(?:^|\/)(公众号|掘金|小红书|共享素材)\/(.+)$/);
  if (projectMarker) {
    return `/api/project-media/${encodedPath(`${projectMarker[1]}/${projectMarker[2]}`)}`;
  }

  if (/^(公众号|掘金|小红书|共享素材)\//.test(value)) {
    return `/api/project-media/${encodedPath(value)}`;
  }
  if (value.startsWith('outputs/')) return `/api/media/${encodedPath(value.slice('outputs/'.length))}`;
  return null;
}

/** 把 markdown 渲染成【已消毒】的 HTML。所有 dangerouslySetInnerHTML 都应走这里，防 XSS。 */
export function renderMarkdown(md: string): string {
  if (!md) return '';
  const raw = marked.parse(md) as string;
  // 先在 DOM 中改写本地文件链接，再交给 DOMPurify 做最终清洗。
  const holder = document.createElement('div');
  holder.innerHTML = raw;
  holder.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((anchor) => {
    const mapped = localFileHref(anchor.getAttribute('href') || '');
    if (mapped) {
      anchor.setAttribute('href', mapped);
      anchor.setAttribute('target', '_blank');
      anchor.setAttribute('rel', 'noreferrer');
    }
  });
  return DOMPurify.sanitize(holder.innerHTML);
}
