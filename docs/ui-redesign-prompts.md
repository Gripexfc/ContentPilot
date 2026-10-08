# CreatorOS UI 重构提示词

这份提示词用于约束 CreatorOS 的全站视觉重构。实现时保留现有业务能力、路由、数据状态和真实/本地能力边界，只重构信息层级、布局、视觉语言和交互反馈。

## 总体提示词

```text
Reading this as: a redesign of a local creator studio for content creators who need to move from signal to publishable draft quickly, with a dark editorial-industrial language, leaning toward a focused CSS design system rather than a generic dashboard.

Use DESIGN_VARIANCE 7, MOTION_INTENSITY 4, VISUAL_DENSITY 4.

Rebuild the entire CreatorOS UI, including the shell, navigation, page headers, cards, forms, empty states, error states, loading states, editors, selectors, status chips, side panels, and legacy pages that share the same components.

Use a single visual theme: graphite black, smoked green surfaces, off-white text, and one acid-lime accent. Do not use purple AI gradients, glassmorphism, decorative blobs, random neon glows, or generic three-card SaaS layouts. Use solid surfaces, thin structural borders, inset highlights, asymmetric grids, visible hierarchy, and a restrained quiet background pattern only when it improves orientation.

The visual metaphor is a signal lab: the sidebar is a dark instrument rail, page headers are briefing surfaces, content cards are evidence panels, and primary actions are lime controls. The UI should feel precise, fast, editorial, and slightly technical without looking like a developer console.

Keep all form labels above fields. Make users enter only the essential information. Prefer select controls, suggested values, segmented choices, datalists, and sensible defaults for everything else. Keep custom entry available when the user needs it.

Every page needs a designed loading state, empty state, inline error state, success state, focus state, disabled state, and mobile collapse. Respect prefers-reduced-motion. Animate only opacity and transform, and only when the motion communicates hierarchy, feedback, or state change.

Use sans-serif display typography for the modern studio direction. Keep headings short, left aligned, and within two lines. Avoid eyebrow labels above every section. Use one accent family consistently across all pages. Ensure all buttons have readable contrast and never wrap on desktop.
```

## 布局提示词

```text
Replace the centered dashboard rhythm with an asymmetric studio layout.

Desktop shell: 224px fixed instrument rail, 64px utility bar, content canvas with a 1180px reading width. Keep the rail visually heavy and the content area quiet.

Page headers: use a left-aligned title block with a short description and a right-side action cluster. Add a thin bottom rule and a small system status line. Do not center the hero.

Discovery page: use a 12-column editorial grid. The first trend board spans 7 columns and two rows, the second spans 5 columns, and the third becomes a full-width evidence strip. Collapse to one column below 768px.

Creation page: use an input column and an output column, but make the output surface visually dominant. Keep the primary topic field above optional context. Use platform and output type as selectable tiles rather than free text.

Breakdown page: put platform selection into a compact control rail and reserve the largest area for the editable result. Empty output must look like an intentional workspace, not a blank card.

Library and profile pages: use a narrow index column plus a wide reading/editing column. Avoid repeated identical cards; use dividers and negative space for hierarchy.

Responsive rules: every multi-column region becomes a single column under 768px. Keep action buttons full width when they become the only control in a row. The sidebar becomes a compact icon rail without hiding the active state.
```

## 主题与画风提示词

```text
Art direction: Night Studio / Signal Lab.

Base: near-black graphite (#0b1110), elevated smoked-green panels (#141d19), quiet dividers (#2b3a32), off-white text (#e8f0e9), moss-muted secondary text (#9aada1).

Accent: one acid-lime signal color (#b7f35a). Use it for primary actions, active navigation, selected controls, key ranks, and success confirmations. Do not introduce a second decorative accent. Error states may use a muted red only as semantic feedback.

Material: matte surfaces, 1px borders, subtle inset top highlights, no floating glass, no black drop shadows on light surfaces, no excessive blur. A faint fixed grid texture may sit behind the shell with pointer-events:none.

Typography: system sans-serif display, heavy but controlled. Large titles use tight tracking and a 1.05 line-height. Body text stays readable and calm. Monospace is reserved for system labels, timestamps, IDs, and status text.

Iconography: keep one icon family and use icons only to clarify actions. No emoji and no decorative icon clusters.
```

## 交互与动效提示词

```text
Motion should feel like a signal being routed, not a marketing animation.

Use short 160–260ms transitions for hover, focus, selection, and active press. Use transform and opacity only. Use a restrained stagger for the first page load and a single reveal for the main output surface.

Loading: use static skeleton rows and panels that match the final layout. Do not use a generic spinner as the only feedback.

Empty: explain what the user can do next and provide one action.

Error: show the cause in context and provide a recovery action. Never hide an API or adapter failure behind a success toast.

Selected controls: use a lime edge, a small signal marker, and stronger text. Do not rely on color alone; preserve a check mark or selected state label.

Reduced motion: disable entry animation, stagger, and perpetual effects under prefers-reduced-motion.
```

## 交付前审查提示词

```text
Before shipping, audit every visible page and shared component.

Check: shell proportions, mobile collapse, focus rings, button contrast, label-above-input order, loading/empty/error/success states, one accent color, no default purple gradients, no em dash in visible UI text, no remote font import, no duplicated CTA intent, no wrapped desktop CTA, no unexplained fake metrics, and no hard-coded credentials.

Open the app in both light and dark system themes. Verify hotspots, creation, breakdown, library, profile, model settings, chat, draft center, publish center, skills, outputs, account settings, and analytics. Run typecheck, tests, and production build after the visual pass.
```
