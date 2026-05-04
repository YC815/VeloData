# VeloData 前端重設計指南
> 目標風格：Editorial Dark（Vercel / Linear 系）+ Sidebar 導覽 + 亮暗模式切換
> 難度標示：🟢 簡單（換個 class）/ 🟡 中等（改幾行）/ 🔴 需要重構（改結構）

---

## 一、設計系統基礎（先建立這些，後面所有修改才有依據）

### 1.1 色彩語意系統（最重要！）

現在的問題：顏色用法沒有規則，TSS 藍、距離綠、時間橘，跟圖表的 CTL 藍、ATL 橘互相撞色，使用者根本搞不清楚「橘色代表什麼」。

**新規則：每種顏色只做一件事**

| 語意 | 暗色模式 Tailwind | 亮色模式 Tailwind | 用在哪裡 |
|------|-----------------|-----------------|---------|
| 體能基礎（CTL） | `text-cyan-400` | `text-cyan-600` | CTL 數字、CTL 圖表線、CTL 徽章 |
| 近期疲勞（ATL） | `text-orange-500` | `text-orange-600` | ATL 數字、ATL 圖表線、ATL 徽章 |
| 狀態好（TSB 正） | `text-emerald-400` | `text-emerald-600` | TSB > 0 的情況 |
| 狀態差（TSB 負） | `text-rose-400` | `text-rose-600` | TSB < -20 的情況 |
| 品牌主色 | `text-orange-500` | `text-orange-600` | 按鈕、logo、hover accent |
| 主文字 | `text-zinc-100` | `text-zinc-900` | 標題、大數字 |
| 次文字 | `text-zinc-400` | `text-zinc-500` | 欄位名稱、說明文字 |
| 輔助文字 | `text-zinc-600` | `text-zinc-400` | 單位、時間戳、placeholder |

> ⚠️ 特別注意：ATL 和 品牌主色都是橘色，但這是刻意的——ATL「最近在燃燒」跟品牌能量感一致。之後若有混淆，可以把 ATL 改成 `amber-400` 做細微區分。

### 1.2 背景層次系統（「玻璃切割」質感的秘密）

Linear 和 Vercel 的高級感不是來自炫酷動畫，是來自背景的精準分層：

```
頁面底 (bg-zinc-950)     ← 最深
  └─ 主容器框 (bg-zinc-900 border-white/8)    ← 輕微浮出
       └─ 卡片 (bg-zinc-800/50 border-white/6)   ← 再浮一層
            └─ 內嵌區塊 (bg-zinc-900 border-white/5)  ← 下沉
```

**換字典（舊 → 新）**

| 舊 class | 新 class | 說明 |
|---------|---------|------|
| `bg-slate-950` | `bg-zinc-950 dark:bg-zinc-950` | 底色，zinc 比 slate 更中性 |
| `bg-slate-900` | `bg-zinc-900` | 一般卡片 |
| `bg-slate-800` | `bg-zinc-800` | 輸入框、次層卡片 |
| `border-slate-800` | `border-white/8` | 卡片邊框（半透明白，更精緻）|
| `border-slate-700` | `border-white/10` | 較明顯的邊框 |
| `bg-slate-900/60` | `bg-zinc-900/70` | 半透明卡片 |

### 1.3 字體層次系統

```
大數字（KPI 主值）：text-4xl font-black tracking-tight font-mono → 第一眼抓到
段落標題：text-sm font-semibold text-zinc-100 uppercase tracking-widest
欄位名稱：text-xs text-zinc-400 uppercase tracking-wider
輔助說明：text-xs text-zinc-600
```

**立即要修的問題**：`Performance Management Chart` 這個英文標題要改成 `體能管理圖` 或刪掉副標全改中文。

---

## 二、佈局架構重構（Sidebar）🔴

這是最大的改動。從「頂部 Tab + 中央內容」改為「左側 Sidebar + 右側內容區」。

### 2.1 為什麼要改

目前 `max-w-4xl mx-auto` 的做法讓頁面在大螢幕上左右各留一大塊空白，資料儀表板不該這樣——空間是用來放更多資料的，不是留白。Sidebar 佈局解決了：
1. 螢幕空間利用率提升
2. 導覽永遠可見，不被 HTMX 換掉
3. Logo 和用戶信息有固定位置

### 2.2 新的 `base.html` 結構

**把整個 `<body>` 內容換成這個：**

```html
<body class="bg-zinc-950 text-zinc-100 font-sans min-h-screen
             transition-colors duration-300
             dark:bg-zinc-950 dark:text-zinc-100">

  <!-- 亮/暗模式初始化（放在最前面避免閃爍） -->
  <script>
    (function() {
      var theme = localStorage.getItem('velodata-theme') || 'dark';
      if (theme === 'light') {
        document.body.classList.add('light-mode');
        document.documentElement.classList.remove('dark');
      } else {
        document.documentElement.classList.add('dark');
      }
    })();
  </script>

  <div class="flex min-h-screen">

    <!-- ─── Sidebar（桌面顯示，手機隱藏）─── -->
    <aside id="sidebar"
      class="hidden lg:flex flex-col w-56 flex-shrink-0
             bg-zinc-900 border-r border-white/8
             fixed top-0 left-0 h-full z-30">

      <!-- Logo 區 -->
      <div class="px-5 pt-6 pb-4 border-b border-white/6">
        <h1 class="text-xl font-black text-orange-500 tracking-tighter leading-none">VeloData</h1>
        <p class="text-[10px] text-zinc-600 mt-1 uppercase tracking-widest">Training Intelligence</p>
      </div>

      <!-- 導覽選項 -->
      <nav id="sidebarNav" class="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {% include 'partials/_sidebar_nav.html' %}
      </nav>

      <!-- 底部：用戶信息 + 主題切換 -->
      <div class="px-4 py-4 border-t border-white/6 space-y-3">
        <!-- 主題切換按鈕 -->
        <button onclick="toggleTheme()"
          class="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg
                 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800
                 transition-colors text-xs font-medium">
          <!-- 暗色模式顯示太陽（切換到亮色） -->
          <svg id="themeIconSun" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/>
          </svg>
          <!-- 亮色模式顯示月亮（切換到暗色） -->
          <svg id="themeIconMoon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/>
          </svg>
          <span id="themeLabel">切換亮色</span>
        </button>

        <!-- 用戶頭像 + 名字 -->
        <div class="flex items-center gap-2.5 px-1">
          {% if athlete.profile %}
          <img src="{{ athlete.profile }}" alt="avatar"
            class="w-7 h-7 rounded-full border border-orange-500/40 object-cover flex-shrink-0" />
          {% else %}
          <div class="w-7 h-7 rounded-full border border-orange-500/40 bg-zinc-800 flex items-center justify-center flex-shrink-0">
            <svg class="w-4 h-4 text-zinc-500" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
            </svg>
          </div>
          {% endif %}
          <div class="min-w-0">
            <p class="text-xs font-semibold text-zinc-200 truncate leading-tight">
              {{ athlete.firstname }} {{ athlete.lastname }}
            </p>
            <p class="text-[10px] text-emerald-500">已連線 Strava</p>
          </div>
        </div>
      </div>
    </aside>

    <!-- ─── 主內容區 ─── -->
    <div class="flex-1 lg:ml-56 min-w-0">

      <!-- 手機版頂部 Header -->
      <header class="lg:hidden flex items-center justify-between px-4 py-3
                     bg-zinc-900/95 border-b border-white/8 backdrop-blur-sm
                     sticky top-0 z-20">
        <h1 class="text-lg font-black text-orange-500 tracking-tighter">VeloData</h1>
        <div class="flex items-center gap-2">
          <button onclick="toggleTheme()" class="p-2 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
            <svg id="mobileThemeIcon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/>
            </svg>
          </button>
          {% if athlete.profile %}
          <img src="{{ athlete.profile }}" class="w-7 h-7 rounded-full border border-orange-500/40 object-cover"/>
          {% endif %}
        </div>
      </header>

      <!-- 工具列（刷新 + 複製 AI） -->
      {% include 'partials/_toolbar.html' %}

      <!-- 手機底部導覽 -->
      <nav id="mobileNav"
        class="lg:hidden fixed bottom-0 left-0 right-0 z-30
               bg-zinc-900/95 border-t border-white/8 backdrop-blur-sm
               flex">
        {% include 'partials/_mobile_nav.html' %}
      </nav>

      <!-- 主內容 -->
      <main id="content" class="px-4 lg:px-8 pt-6 pb-24 lg:pb-8 max-w-6xl">
        {% block content %}{% endblock %}
      </main>
    </div>

  </div>

  <!-- Scripts -->
  <script src="{{ url_for('static', filename='js/copy_for_ai.js') }}"></script>
  <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
  {% block scripts %}{% endblock %}

  <!-- HTMX Loading skeleton -->
  <script>
    document.body.addEventListener('htmx:beforeRequest', function (e) {
      if (!e.detail.target || e.detail.target.id !== 'content') return;
      e.detail.target.innerHTML =
        '<div class="animate-pulse space-y-4 py-2">' +
          '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">' +
            '<div class="h-32 bg-zinc-800/60 rounded-2xl"></div>' +
            '<div class="h-32 bg-zinc-800/60 rounded-2xl"></div>' +
          '</div>' +
          '<div class="h-20 bg-zinc-800/60 rounded-2xl"></div>' +
          '<div class="h-72 bg-zinc-800/60 rounded-2xl"></div>' +
        '</div>';
    });
  </script>
</body>
```

### 2.3 新建 `_sidebar_nav.html`（取代原本的 `_nav_tabs.html`）

```html
<!-- templates/partials/_sidebar_nav.html -->
{% set nav_items = [
  ('dashboard',  '/partials/dashboard', '/',         '儀表板',   'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'),
  ('analysis',   '/partials/analysis',  '/analysis', '體能分析',  'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4v16'),
  ('racing',     '/partials/racing',    '/racing',   '賽事規劃',  'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7'),
  ('profile',    '/partials/profile',   '/profile',  '個人設定',  'M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z'),
] %}

{% for tab_id, hx_url, push_url, label, icon_path in nav_items %}
<button
  hx-get="{{ hx_url }}"
  hx-target="#content"
  hx-push-url="{{ push_url }}"
  hx-on:click="setActiveNav(this)"
  class="sidebar-nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
    {% if active_tab == tab_id %}
      bg-orange-500/15 text-orange-400 border border-orange-500/20
    {% else %}
      text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 border border-transparent
    {% endif %}"
>
  <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="{{ icon_path }}"/>
  </svg>
  {{ label }}
</button>
{% endfor %}

<script>
function setActiveNav(el) {
  document.querySelectorAll('.sidebar-nav-item').forEach(function(item) {
    item.classList.remove('bg-orange-500/15', 'text-orange-400', 'border-orange-500/20');
    item.classList.add('text-zinc-500', 'hover:text-zinc-200', 'hover:bg-zinc-800', 'border-transparent');
  });
  el.classList.add('bg-orange-500/15', 'text-orange-400', 'border-orange-500/20');
  el.classList.remove('text-zinc-500', 'hover:text-zinc-200', 'hover:bg-zinc-800', 'border-transparent');
  // 同步更新手機版底部導覽
  var tabId = el.getAttribute('hx-get').replace('/partials/', '');
  document.querySelectorAll('.mobile-nav-item').forEach(function(item) {
    item.classList.toggle('text-orange-400', item.dataset.tab === tabId);
    item.classList.toggle('text-zinc-500', item.dataset.tab !== tabId);
  });
}
</script>
```

### 2.4 新建 `_mobile_nav.html`（手機底部導覽）

```html
<!-- templates/partials/_mobile_nav.html -->
{% set nav_items = [
  ('dashboard', '/partials/dashboard', '/', 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', '儀表板'),
  ('analysis',  '/partials/analysis',  '/analysis', 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4v16', '體能'),
  ('racing',    '/partials/racing',    '/racing',   'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7', '賽事'),
  ('profile',   '/partials/profile',   '/profile',  'M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z', '設定'),
] %}

{% for tab_id, hx_url, push_url, icon_path, label in nav_items %}
<button
  hx-get="{{ hx_url }}"
  hx-target="#content"
  hx-push-url="{{ push_url }}"
  hx-on:click="setActiveNav(document.querySelector('[hx-get=\'{{ hx_url }}\']:not(.mobile-nav-item)'))"
  data-tab="{{ tab_id }}"
  class="mobile-nav-item flex-1 flex flex-col items-center justify-center py-2 gap-1 transition-colors
    {% if active_tab == tab_id %}text-orange-400{% else %}text-zinc-500{% endif %}"
>
  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="{{ icon_path }}"/>
  </svg>
  <span class="text-[10px] font-medium">{{ label }}</span>
</button>
{% endfor %}
```

### 2.5 新建 `_toolbar.html`（原本 header 的刷新 + 複製按鈕）

```html
<!-- templates/partials/_toolbar.html -->
<!-- 工具列：出現在主內容區頂部，sidebar 右方 -->
<div class="flex items-center justify-between px-4 lg:px-8 py-3 border-b border-white/6">
  <!-- 當前頁面標題（由 HTMX 切換時透過 JS 更新） -->
  <h2 id="pageTitle" class="text-sm font-semibold text-zinc-300">儀表板</h2>

  <div class="flex items-center gap-2">
    <!-- 快取時間 -->
    <span id="cacheTimeLabel" class="hidden sm:block text-xs text-zinc-600 font-mono"></span>

    <!-- 刷新按鈕 -->
    <button
      id="refreshDataBtn"
      onclick="refreshActivityData()"
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
             bg-zinc-800 border border-white/8
             hover:bg-zinc-700 hover:border-white/15
             text-zinc-400 hover:text-zinc-200
             text-xs font-medium transition-all"
    >
      <svg id="refreshIcon" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
      </svg>
      <span id="refreshLabel">刷新</span>
    </button>

    <!-- 複製給 AI -->
    <button
      id="copyAiBtn"
      onclick="copyForAI()"
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
             bg-zinc-800 border border-white/8
             hover:bg-zinc-700 hover:border-white/15
             text-zinc-400 hover:text-zinc-200
             text-xs font-medium transition-all"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
      </svg>
      <span id="copyAiLabel">複製給 AI</span>
    </button>
  </div>
</div>

<script>
  /* 刷新邏輯（從 _header.html 搬過來，邏輯不變） */
  function _updateCacheTimeLabel(cachedAt) {
    var label = document.getElementById('cacheTimeLabel');
    if (label) {
      label.textContent = cachedAt ? cachedAt : '';
      label.classList.toggle('hidden', !cachedAt);
    }
  }
  function _getActiveTabUrl() {
    var active = document.querySelector('.sidebar-nav-item.text-orange-400');
    return active ? active.getAttribute('hx-get') : '/partials/dashboard';
  }
  function refreshActivityData() {
    var btn = document.getElementById('refreshDataBtn');
    var icon = document.getElementById('refreshIcon');
    var label = document.getElementById('refreshLabel');
    if (!btn) return;
    btn.disabled = true;
    label.textContent = '更新中…';
    icon.classList.add('animate-spin');
    fetch('/api/activities/refresh', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.cached_at) _updateCacheTimeLabel(data.cached_at);
        htmx.ajax('GET', _getActiveTabUrl(), { target: '#content', swap: 'innerHTML' });
      })
      .catch(function() { label.textContent = '失敗'; })
      .finally(function() {
        btn.disabled = false;
        label.textContent = '刷新';
        icon.classList.remove('animate-spin');
      });
  }
  fetch('/api/activities/cache-info')
    .then(function(r) { return r.json(); })
    .then(function(d) { _updateCacheTimeLabel(d.cached_at); })
    .catch(function() {});
</script>
```

---

## 三、亮暗模式實作 🟡

### 3.1 新建 `static/js/theme.js`

```javascript
// static/js/theme.js
// 使用 localStorage 記住使用者偏好，body 加 class 切換
(function() {
  var THEME_KEY = 'velodata-theme';

  function applyTheme(theme) {
    var body = document.body;
    var sunIcon = document.getElementById('themeIconSun');
    var moonIcon = document.getElementById('themeIconMoon');
    var label = document.getElementById('themeLabel');
    var mobileIcon = document.getElementById('mobileThemeIcon');

    if (theme === 'light') {
      body.classList.add('light-mode');
      body.style.setProperty('--bg-base', '#fafafa');
      body.style.setProperty('--bg-card', '#ffffff');
      body.style.setProperty('--border', 'rgba(0,0,0,0.08)');
      body.style.setProperty('--text-primary', '#09090b');
      body.style.setProperty('--text-secondary', '#71717a');
      body.style.setProperty('--text-muted', '#a1a1aa');
      if (sunIcon) sunIcon.classList.remove('hidden');
      if (moonIcon) moonIcon.classList.add('hidden');
      if (label) label.textContent = '切換暗色';
      // 手機版圖示換成太陽（代表目前是亮色，點了切換暗色）
      if (mobileIcon) mobileIcon.innerHTML =
        '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/>';
    } else {
      body.classList.remove('light-mode');
      body.style.removeProperty('--bg-base');
      body.style.removeProperty('--bg-card');
      if (sunIcon) sunIcon.classList.add('hidden');
      if (moonIcon) moonIcon.classList.remove('hidden');
      if (label) label.textContent = '切換亮色';
      if (mobileIcon) mobileIcon.innerHTML =
        '<path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/>';
    }
  }

  window.toggleTheme = function() {
    var current = localStorage.getItem(THEME_KEY) || 'dark';
    var next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  };

  // 頁面載入時套用
  var saved = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(saved);
})();
```

### 3.2 亮色模式 CSS（加到 `<head>` 裡）

```html
<!-- 加在 base.html 的 <head> 裡，Tailwind CDN 載入後 -->
<style>
  /* 亮色模式覆寫 */
  .light-mode {
    background-color: #f4f4f5 !important; /* zinc-100 */
    color: #09090b !important;
  }
  .light-mode [class*="bg-zinc-950"] { background-color: #f4f4f5 !important; }
  .light-mode [class*="bg-zinc-900"] { background-color: #ffffff !important; }
  .light-mode [class*="bg-zinc-800"] { background-color: #f4f4f5 !important; }
  .light-mode [class*="border-white/"] { border-color: rgba(0,0,0,0.08) !important; }
  .light-mode [class*="text-zinc-100"] { color: #09090b !important; }
  .light-mode [class*="text-zinc-400"] { color: #71717a !important; }
  .light-mode [class*="text-zinc-500"] { color: #71717a !important; }
  .light-mode [class*="text-zinc-600"] { color: #a1a1aa !important; }
  .light-mode aside { background-color: #ffffff !important; border-color: rgba(0,0,0,0.08) !important; }
  .light-mode #mobileNav { background-color: rgba(255,255,255,0.95) !important; border-color: rgba(0,0,0,0.08) !important; }

  /* CTL/ATL 亮色調整 */
  .light-mode .ctl-value { color: #0891b2 !important; }  /* cyan-600 */
  .light-mode .atl-value { color: #ea580c !important; }  /* orange-600 */
  .light-mode .tsb-positive { color: #059669 !important; } /* emerald-600 */
  .light-mode .tsb-negative { color: #e11d48 !important; } /* rose-600 */

  /* 平滑過渡 */
  body, aside, nav, main, .bg-zinc-900, .bg-zinc-800, .bg-zinc-950 {
    transition: background-color 0.3s ease, color 0.2s ease, border-color 0.3s ease;
  }
</style>
```

> 💡 **為什麼用 CSS class 而不是 Tailwind `dark:` variants？**
> 因為 Tailwind CDN 版本不支援動態 purge，`dark:` variants 需要設定檔。用 `.light-mode` class + CSS 覆寫是最快速可行的方案，不需要 build step。

---

## 四、各頁面元件修改細項

### 4.1 Login 頁面 🟢

**問題**：功能只有連結 Strava，但視覺空洞，沒有體現 VeloData 是什麼。

**改法**：

```html
<!-- templates/login.html 重寫 -->
<body class="bg-zinc-950 text-zinc-100 font-sans flex items-center justify-center min-h-screen">

  <!-- 背景裝飾：極淡的 grid 線條（編輯設計風常見手法） -->
  <div class="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:64px_64px] pointer-events-none"></div>

  <div class="relative text-center px-6 max-w-sm w-full">
    <!-- Logo 區 -->
    <div class="mb-8">
      <h1 class="text-6xl font-black text-orange-500 tracking-tighter mb-2 leading-none">VeloData</h1>
      <p class="text-zinc-500 text-sm">單車訓練數據監控</p>
    </div>

    <!-- 三個特色（視覺錨點） -->
    <div class="grid grid-cols-3 gap-3 mb-8 text-center">
      <div class="bg-zinc-900 border border-white/8 rounded-xl p-3">
        <p class="text-cyan-400 font-black text-xl font-mono leading-none">CTL</p>
        <p class="text-zinc-600 text-[10px] mt-1">體能追蹤</p>
      </div>
      <div class="bg-zinc-900 border border-white/8 rounded-xl p-3">
        <p class="text-orange-500 font-black text-xl font-mono leading-none">TSS</p>
        <p class="text-zinc-600 text-[10px] mt-1">訓練壓力</p>
      </div>
      <div class="bg-zinc-900 border border-white/8 rounded-xl p-3">
        <p class="text-emerald-400 font-black text-xl font-mono leading-none">FTP</p>
        <p class="text-zinc-600 text-[10px] mt-1">功率估算</p>
      </div>
    </div>

    <!-- 錯誤訊息 -->
    {% if error %}
    <div class="bg-rose-950/60 border border-rose-800/50 text-rose-300 text-sm rounded-xl px-5 py-3 mb-5">
      {{ error }}
    </div>
    {% endif %}

    <!-- 連結按鈕 -->
    <a href="/auth"
      class="flex items-center justify-center gap-3
             bg-orange-500 hover:bg-orange-400 active:bg-orange-600
             text-white font-bold px-8 py-3.5 rounded-xl text-base
             transition-all shadow-lg shadow-orange-500/20 hover:shadow-orange-500/30 hover:-translate-y-0.5">
      <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.172"/>
      </svg>
      連結 Strava 帳號
    </a>

    <p class="text-zinc-700 text-xs mt-5">授權後 refresh token 自動存入 .env</p>
  </div>
</body>
```

### 4.2 訓練狀態卡片（`_kpi_training_status.html`）🟢

**問題**：TSB 數字顏色邏輯正確，但沒有用新的語意色系；CTL/ATL 徽章用藍色/橘色，和 PMC 圖表顏色不同。

**把這幾個 class 換掉：**

```diff
- <span class="bg-blue-900/40 border border-blue-800/50 text-blue-300 text-xs ...">CTL {{ pmc.current_ctl }}</span>
+ <span class="bg-cyan-950/40 border border-cyan-900/30 text-cyan-400 text-xs ... ctl-value">CTL {{ pmc.current_ctl }}</span>

- <span class="bg-orange-900/40 border border-orange-800/50 text-orange-300 text-xs ...">ATL {{ pmc.current_atl }}</span>
+ <span class="bg-orange-950/40 border border-orange-900/30 text-orange-500 text-xs ... atl-value">ATL {{ pmc.current_atl }}</span>
```

**TSB 數字顏色（把 if-elif 邏輯換成語意色）：**

```diff
- {% if tsb_status.color == 'green' %}text-green-400
- {% elif tsb_status.color == 'yellow' %}text-yellow-400
- {% elif tsb_status.color == 'orange' %}text-orange-400
- {% else %}text-red-400{% endif %}
+ {% if pmc.current_tsb >= 5 %}text-emerald-400 tsb-positive
+ {% elif pmc.current_tsb >= 0 %}text-zinc-200
+ {% elif pmc.current_tsb >= -20 %}text-amber-400
+ {% else %}text-rose-400 tsb-negative{% endif %}
```

**加上 CTL 光暈效果（編輯設計風）：**

```diff
- <div class="bg-slate-900 p-5 rounded-2xl border border-slate-800 shadow-xl">
+ <div class="bg-zinc-900 p-5 rounded-2xl border border-white/8 relative overflow-hidden">
+   <!-- 背景光暈：TSB 正值時顯示綠光，負值顯示紅光 -->
+   <div class="absolute -top-8 -right-8 w-24 h-24 rounded-full blur-2xl opacity-20
+     {% if pmc.current_tsb >= 0 %}bg-emerald-500{% else %}bg-rose-500{% endif %}
+     pointer-events-none"></div>
```

### 4.3 PMC 圖表卡片（`_pmc_chart.html`）🟢

**問題**：英文標題、CTL/ATL 徽章用錯色系、圖表高度 `h-56` 太小。

**修改步驟：**

1. **改標題**（第 4 行）：
```diff
- <h2 class="text-lg font-bold text-slate-300">Performance Management Chart</h2>
- <p class="text-xs text-slate-500 mt-0.5">過去 42 天體能管理趨勢</p>
+ <h2 class="text-lg font-bold text-zinc-200">體能管理圖</h2>
+ <p class="text-xs text-zinc-500 mt-0.5">CTL / ATL / TSB 過去 42 天</p>
```

2. **換 CTL/ATL 徽章色**：
```diff
- <span class="bg-blue-900/40 border border-blue-800/50 text-blue-300 ...">CTL {{ pmc.current_ctl }}</span>
+ <span class="bg-cyan-950/40 border border-cyan-900/30 text-cyan-400 ... ctl-value">CTL {{ pmc.current_ctl }}</span>

- <span class="bg-orange-900/40 border border-orange-800/50 text-orange-300 ...">ATL {{ pmc.current_atl }}</span>
+ <span class="bg-orange-950/40 border border-orange-900/30 text-orange-500 ... atl-value">ATL {{ pmc.current_atl }}</span>
```

3. **加高圖表**：
```diff
- <div class="relative h-56">
+ <div class="relative h-64">
```

4. **同步更新 `pmc_chart.js` 的顏色**（第幾行找 color 設定換掉）：
```javascript
// 找到 datasets 裡的 CTL 設定，換成 cyan
borderColor: 'rgb(34, 211, 238)',  // cyan-400
// ATL 保持 orange
borderColor: 'rgb(249, 115, 22)',  // orange-500
// TSB 正值 emerald，負值 rose（Chart.js 的 segment callback 邏輯不變，換色碼即可）
```

### 4.4 本週統計卡片（`_weekly_stats.html`）🟢

**問題**：3 張卡片各用不同顏色（藍/綠/橘），沒有語意，只是「三種顏色」。

**新策略**：數字全用 `text-zinc-100`（白），類別名稱和單位用 `text-zinc-500`。讓「大白數字」本身就夠突出，不需要靠顏色分類。

```diff
- <p class="text-3xl font-bold text-blue-400">{{ weekly_tss }}</p>
+ <p class="text-4xl font-black font-mono text-zinc-100 tracking-tight">{{ weekly_tss }}</p>

- <p class="text-3xl font-bold text-green-400">{{ weekly_km }} <span class="text-lg font-normal text-slate-400">km</span></p>
+ <p class="text-4xl font-black font-mono text-zinc-100 tracking-tight">{{ weekly_km }}<span class="text-sm font-normal text-zinc-500 ml-1">km</span></p>

- <p class="text-3xl font-bold text-orange-400">{{ weekly_time }}</p>
+ <p class="text-4xl font-black font-mono text-zinc-100 tracking-tight">{{ weekly_time }}</p>
```

**卡片本身也換 class**：
```diff
- <div class="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
+ <div class="bg-zinc-900 p-5 rounded-2xl border border-white/8 hover:border-white/15 transition-colors">
```

### 4.5 活動卡片 Grid（`_activity_grid.html`）🟡

**問題**：`gap-px bg-slate-800` 製造的「格子分隔線」感覺是把表格塞進卡片，視覺質感不好。

**改法：把格子分隔線改成純空間分隔**

```diff
- <div class="grid grid-cols-2 gap-px bg-slate-800 border-t border-slate-800 flex-1">
-   <div class="bg-slate-900/80 px-3 py-2.5">
+ <div class="grid grid-cols-2 gap-0 border-t border-white/6 flex-1">
+   <div class="px-3 py-2.5 border-r border-white/6">
```

```diff
- <div class="act-card bg-slate-900/60 rounded-2xl border border-slate-800 hover:border-slate-700 hover:bg-slate-800/60 transition flex flex-col"
+ <div class="act-card bg-zinc-900/80 rounded-2xl border border-white/8 hover:border-white/15 hover:bg-zinc-800/50 transition-all flex flex-col group"
```

**TSS 數字（黃色改白色，讓顏色讓位給結構）：**
```diff
- <div class="text-yellow-400 font-mono font-bold text-lg leading-none">{{ act.tss }}</div>
+ <div class="text-zinc-100 font-mono font-bold text-xl leading-none">{{ act.tss }}</div>
- <div class="text-xs text-slate-500 mt-0.5">TSS</div>
+ <div class="text-[10px] text-zinc-600 mt-0.5 uppercase tracking-wider">TSS</div>
```

**功率區改用 cyan**（跟 CTL 語意一致，「功率 = 體能輸出」）：
```diff
- <div class="text-sm font-mono font-semibold text-orange-300">
+ <div class="text-sm font-mono font-semibold text-cyan-400">
```

### 4.6 FTP 估算卡片（`_ftp_suggest_card.html`）🟢

**主要改動**：把 `col-span-5` 的不均等 grid（2+2+1）改成更清晰的 3 格佈局。

```diff
- <div class="grid grid-cols-5 gap-3 mb-4">
-   <div class="col-span-2 bg-orange-950/30 ...">
-   <div id="ftpFinalCell" class="col-span-2 ...">
-   <div id="ftpDeltaCell" class="col-span-1 ...">
+ <div class="grid grid-cols-3 gap-3 mb-4">
+   <div class="bg-zinc-800/60 border border-white/8 rounded-xl p-3 text-center"><!-- 目前 FTP -->
+   <div id="ftpFinalCell" class="bg-zinc-800/60 border border-white/8 rounded-xl p-3 text-center"><!-- 建議 FTP -->
+   <div id="ftpDeltaCell" class="bg-zinc-800/60 border border-white/8 rounded-xl p-3 text-center"><!-- 差值 -->
```

**目前 FTP 數字換顏色**（橘色是 ATL/疲勞色，FTP 應該用 cyan 代表「體能潛力」）：
```diff
- <div id="ftpCurrentVal" class="text-2xl font-mono font-bold text-orange-200">—</div>
+ <div id="ftpCurrentVal" class="text-2xl font-mono font-bold text-cyan-400 ctl-value">—</div>
```

### 4.7 賽事倒數卡片（`_race_countdown.html`）🟢

**問題**：`text-base font-bold` 的倒數天數太小。這是 Dashboard 上最重要的即時資訊，數字要更大更跳出。

```diff
- <p class="text-base font-bold text-red-400 font-mono leading-none">今天！</p>
+ <p class="text-2xl font-black text-rose-400 font-mono leading-none">今天！</p>

- <p class="text-base font-bold text-orange-400 font-mono leading-none">{{ target_race.days_until }}</p>
+ <p class="text-3xl font-black text-orange-500 font-mono leading-none">{{ target_race.days_until }}</p>
- <p class="text-[10px] text-slate-500">天後</p>
+ <p class="text-xs text-zinc-500 leading-none mt-0.5">天後</p>
```

**卡片邊框改成 orange glow 效果**：
```diff
- <div class="bg-slate-900 border border-orange-500/30 rounded-2xl p-5 shadow-lg">
+ <div class="bg-zinc-900 border border-orange-500/25 rounded-2xl p-5 relative overflow-hidden
+             shadow-lg shadow-orange-500/5">
+   <div class="absolute -bottom-6 -right-6 w-20 h-20 rounded-full blur-2xl opacity-10 bg-orange-500 pointer-events-none"></div>
```

**空態改法（更有視覺引導性）**：
```diff
- <div class="bg-slate-900/40 border border-slate-800 border-dashed rounded-2xl p-6 flex flex-col items-center justify-center text-center gap-2 min-h-[152px]">
+ <div class="border border-white/6 border-dashed rounded-2xl p-6 flex flex-col items-center justify-center text-center gap-2 min-h-[152px] bg-zinc-900/30">
```

### 4.8 Profile 頁面（`_content_profile.html`）🟢

**問題**：輸入框 padding 太大（`py-2.5` 配 `text-lg` 讓它看起來笨重），「裝置設定」佔位卡片讓版面顯得未完成。

**輸入框改小**：
```diff
- class="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 font-mono text-lg ..."
+ class="w-full bg-zinc-800 border border-white/10 rounded-lg px-4 py-2 text-zinc-100 font-mono text-base
+        focus:outline-none focus:border-orange-500/60 focus:ring-1 focus:ring-orange-500/20 transition-all"
```

**移除「裝置設定」佔位卡片**（它只是讓頁面看起來未完成）：
```diff
- <div class="bg-slate-900/40 border border-slate-800 border-dashed rounded-2xl p-6">
-   <h3 class="text-slate-400 text-xs uppercase tracking-widest mb-2">裝置設定</h3>
-   <p class="text-slate-600 text-sm">功率計裝置設定開發中</p>
- </div>
+ <!-- 移除，等功能做好再加 -->
```

**儲存按鈕加 hover shadow**：
```diff
- class="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-400 text-white font-semibold text-sm transition disabled:opacity-50"
+ class="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-400 active:bg-orange-600
+        text-white font-semibold text-sm transition-all
+        shadow-md shadow-orange-500/20 hover:shadow-orange-500/30 hover:-translate-y-0.5
+        disabled:opacity-50 disabled:shadow-none disabled:translate-y-0"
```

---

## 五、細節增強（Editorial 質感的關鍵）

### 5.1 按鈕統一風格

所有次要按鈕（刷新、複製、套用等）統一換成：
```html
class="... bg-zinc-800 border border-white/8 hover:bg-zinc-700 hover:border-white/15 transition-all"
```

主要 CTA 按鈕（新增賽事、估算 FTP 等）統一換成：
```html
class="... bg-orange-500 hover:bg-orange-400 active:bg-orange-600
       shadow-sm shadow-orange-500/20 hover:shadow-orange-500/30
       hover:-translate-y-0.5 transition-all"
```

### 5.2 空態視覺統一

所有空態（無賽事、無資料等）換成統一樣式：
```html
<div class="flex flex-col items-center justify-center py-12 text-center">
  <!-- 圖示用超大、超淡 -->
  <div class="w-12 h-12 rounded-2xl bg-zinc-800/60 border border-white/6
              flex items-center justify-center mb-3">
    <svg class="w-6 h-6 text-zinc-700" .../>
  </div>
  <p class="text-sm text-zinc-500">提示文字</p>
  <p class="text-xs text-zinc-700 mt-1">次要說明</p>
</div>
```

### 5.3 Tooltip 統一樣式

所有 tooltip 換成：
```html
class="absolute ... w-72 bg-zinc-900 border border-white/10 rounded-xl px-4 py-3
       text-xs text-zinc-300 leading-relaxed shadow-2xl shadow-black/50
       opacity-0 group-hover:opacity-100 transition-opacity duration-200
       pointer-events-none z-50"
```

---

## 六、修改優先順序建議

| 優先 | 改什麼 | 效果 | 難度 |
|------|--------|------|------|
| 1 | 把所有 `slate-*` 換成 `zinc-*` | 整體質感立刻提升 | 🟢 全局搜尋替換 |
| 2 | 把所有 `border-slate-800` 換成 `border-white/8` | 邊框變精緻 | 🟢 全局替換 |
| 3 | CTL 改 cyan、ATL 保留 orange（但換色階） | 顏色語意清晰 | 🟢 各換幾個 class |
| 4 | 週統計大數字換成 `text-4xl font-black text-zinc-100` | 數字跳出 | 🟢 換 3 行 |
| 5 | 新增 `theme.js` + 主題切換按鈕 | 亮暗模式上線 | 🟡 新建 1 個 JS 檔案 |
| 6 | Login 頁面重寫 | 第一印象大幅提升 | 🟡 改 1 個檔案 |
| 7 | Sidebar 佈局重構 | 最大視覺升級 | 🔴 需要改 base.html + 新建幾個 partial |

---

## 七、完整 class 替換速查表

做全局搜尋替換（`grep -r "舊class" templates/` 找到後批量換）：

```
bg-slate-950   →   bg-zinc-950
bg-slate-900   →   bg-zinc-900
bg-slate-800   →   bg-zinc-800
bg-slate-700   →   bg-zinc-700
text-slate-100 →   text-zinc-100
text-slate-200 →   text-zinc-200
text-slate-300 →   text-zinc-300
text-slate-400 →   text-zinc-400
text-slate-500 →   text-zinc-500
text-slate-600 →   text-zinc-600
text-slate-700 →   text-zinc-700
border-slate-800 → border-white/8
border-slate-700 → border-white/10
border-slate-600 → border-white/15
divide-slate-800 → divide-white/8
```

> ⚠️ 注意：`text-blue-*`、`text-green-*`、`text-yellow-*` 是語意色（CTL/TSB 等），**不要盲目替換**，要按照第一章的色彩語意系統手動確認。
