# 知序 UI 原型

这是一个与现有 React 业务页面隔离的静态视觉原型。它只演示应用 Shell、侧栏、顶部工具栏、我的画像、内容工作区、状态卡片、弹窗、Toast、空状态和 Logo，不读取后端，也不会改动业务数据。

## 预览

直接打开 `zixu-ui.html` 即可预览。

如果希望通过 Vite 的静态目录访问：

```bash
cd /Users/fc/Desktop/CreatorOS/web/frontend
npm run dev
```

然后打开 http://localhost:5173/prototype/zixu-ui.html。

也可以在项目根目录运行一个只读静态服务器：

```bash
python3 -m http.server 4173 --directory /Users/fc/Desktop/CreatorOS/web/frontend/public
```

然后打开 http://localhost:4173/prototype/zixu-ui.html。

## 交互

- 左侧导航可以切换总览、我的画像、内容工作区等视图。
- “查看版本历史”打开弹窗。
- 保存、采纳建议、添加来源等动作会显示 Toast。
- 小屏幕会把侧栏收缩为图标栏，工作区按单列排列。
