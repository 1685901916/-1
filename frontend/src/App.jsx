import { useEffect, useMemo, useRef, useState } from "react";

const fallbackData = {
  product_name: "漫画画质提升",
  tagline: "本地漫画拆分、画质增强与多格式导出工作台",
  source_root: "",
  default_output_root: "",
  export_options: [],
  source_books: [],
  jobs: [],
};

const pageContent = {
  import: {
    heroTitle: "导入",
    heroText: "本地漫画增强与多格式导出工作台",
    kicker: "拖拽导入",
    cardTitle: "把漫画拖到这里",
    cardText: "支持 MOBI / PDF / CBZ / EPUB / 图片文件夹",
    cardHint: "先加入批处理列表，再到导出页设置目录和格式。",
  },
  split: {
    heroTitle: "拆图",
    heroText: "把漫画文件拆成标准 pages 图片序列，供增强和导出继续使用。",
    kicker: "拆图模块",
    cardTitle: "把漫画拆成 pages 图片",
    cardText: "选中素材后执行拆图，系统会把 PDF、MOBI、EPUB、CBZ、ZIP 或图片目录整理成连续页。",
    cardHint: "拆图完成后，可以继续执行画质提升或直接导出。",
  },
  enhance: {
    heroTitle: "提升",
    heroText: "对现有页面执行增强，输出 pages_ai 增强图。",
    kicker: "画质提升",
    cardTitle: "把 pages 提升成 pages_ai",
    cardText: "优先读取拆图结果 pages；如果素材本身就是图片目录，也可以直接增强。",
    cardHint: "是否保留原图和增强图，由执行设置页统一控制。",
  },
  export: {
    heroTitle: "导出",
    heroText: "本地漫画增强与多格式导出工作台",
    kicker: "导出设置",
    cardTitle: "先定导出目录和格式",
  },
  settings: {
    heroTitle: "执行设置",
    heroText: "本地漫画拆图、图片增强与多格式导出工作台",
  },
  tasks: {
    heroTitle: "任务结果",
    heroText: "查看任务进度、日志、错误与输出文件，并打开详情。",
  },
  taskDetail: {
    heroTitle: "任务详情",
    heroText: "查看当前任务的进度、输出文件、日志与错误信息。",
  },
};

const stageLabelMap = {
  split: "拆图模块",
  import: "导入素材",
  analyze: "质量分析",
  enhance_module: "画质提升",
  enhance: "画质提升",
  optimize: "页面整理",
  export_module: "导出模块",
  package: "导出模块",
  export: "导出完成",
  full: "完整流程",
};

const statusLabelMap = {
  queued: "等待中",
  running: "执行中",
  ready: "已完成",
  failed: "失败",
  processed: "已处理",
  idle: "空闲",
};

const formatMeta = {
  cbz: {
    label: "CBZ",
    description: "高质量漫画归档，适合平板阅读和收藏。",
    fit: "校验与收藏",
    ratio: 2.52,
  },
  zip: {
    label: "ZIP",
    description: "与 CBZ 内容一致，适合手动检查与通用压缩流程。",
    fit: "兼容读取",
    ratio: 2.46,
  },
  epub: {
    label: "EPUB",
    description: "适合安卓平板与通用电子书阅读器。",
    fit: "通用阅读",
    ratio: 1.91,
  },
  mobi: {
    label: "MOBI",
    description: "适合 Kindle 或旧版 mobi 生态。",
    fit: "Kindle 兼容",
    ratio: 1.74,
  },
  pdf: {
    label: "PDF",
    description: "按页固化导出，适合分享、打印与快速预览。",
    fit: "分享与打印",
    ratio: 2.08,
  },
};

const deviceOptions = [
  { value: "android-tablet", label: "安卓平板", multiplier: 1 },
  { value: "general-reader", label: "通用阅读器", multiplier: 0.94 },
  { value: "kindle", label: "Kindle", multiplier: 0.86 },
];

const enhancerMeta = {
  "realesrgan-anime": {
    label: "realesrgan-anime",
    title: "Real-ESRGAN Anime",
    description: "高质量动漫增强，适合细节更丰富的页面。",
  },
  waifu2x: {
    label: "waifu2x",
    title: "waifu2x",
    description: "动漫专用 AI 超分，线条清晰锐利，适合作为默认增强。",
  },
  opencv: {
    label: "opencv",
    title: "opencv",
    description: "无需额外模型，速度快，适合作为兼容兜底。",
  },
};

const acceptInput = ".mobi,.cbz,.zip,.pdf,.epub";
const storagePrefix = "manga-ui.";
const validPages = new Set(["import", "split", "enhance", "export", "settings", "tasks", "task-detail"]);
const imageFormatOptions = [
  { value: "jpg", label: "JPG" },
  { value: "png", label: "PNG" },
  { value: "webp", label: "WEBP" },
];
const pdfQualityOptions = [
  { value: "fast_auto", label: "体积优先", hint: "JPG/WEBP 更小，适合批量导出" },
  { value: "quality_auto", label: "均衡", hint: "保留更多细节，体积适中" },
  { value: "lossless", label: "高保真", hint: "优先保留质量，文件会更大" },
];
const waifuNoiseOptions = [
  { value: -1, label: "关闭降噪" },
  { value: 0, label: "弱降噪" },
  { value: 1, label: "标准" },
  { value: 2, label: "偏强" },
  { value: 3, label: "最强" },
];

const readJson = (response) => response.json().catch(() => ({}));

function readStoredValue(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(`${storagePrefix}${key}`);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeStoredValue(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${storagePrefix}${key}`, JSON.stringify(value));
  } catch {}
}

function readPageFromHash() {
  if (typeof window === "undefined") return "import";
  const page = window.location.hash.replace(/^#/, "").trim();
  return validPages.has(page) ? page : "import";
}

function formatStage(stage) {
  return stageLabelMap[stage] || stage || "-";
}

function formatStatus(status) {
  return statusLabelMap[status] || status || "-";
}

function formatSize(sizeMb) {
  if (sizeMb == null || Number.isNaN(Number(sizeMb))) return "-";
  const value = Number(sizeMb);
  if (value >= 1024) return `${(value / 1024).toFixed(1)} GB`;
  if (value > 0 && value < 0.1) return `${Math.max(1, Math.round(value * 1024))} KB`;
  return `${value.toFixed(value >= 100 ? 0 : 1)} MB`;
}

function formatSourceType(type) {
  if (!type) return "未知";
  if (type === "folder") return "图片目录";
  return String(type).toUpperCase();
}

function baseName(value) {
  if (!value) return "";
  return value.split(/[\\/]/).filter(Boolean).pop() || value;
}

function calculateEstimateSize(baseSizeMb, ratio, multiplier) {
  return Number(((baseSizeMb || 0) * ratio * multiplier).toFixed(1));
}

function estimateOutputRangeMb(source, outputFormat, options) {
  const baseSize = Number(source?.size_mb || 0);
  if (!(baseSize > 0)) return { low: 0, high: 0 };

  const outputProfiles = {
    cbz: { base: 1.0, variance: 0.14 },
    zip: { base: 0.97, variance: 0.14 },
    epub: { base: 0.88, variance: 0.18 },
    mobi: { base: 0.81, variance: 0.2 },
    pdf: { base: 1.06, variance: 0.22 },
  };
  const inputFactors = {
    folder: 1.0,
    cbz: 0.84,
    zip: 0.84,
    pdf: 0.7,
    epub: 0.78,
    mobi: 0.74,
  };
  const imageFactors = {
    jpg: { fast_auto: 0.78, quality_auto: 0.92, lossless: 1.06 },
    webp: { fast_auto: 0.68, quality_auto: 0.82, lossless: 0.95 },
    png: { fast_auto: 1.38, quality_auto: 1.42, lossless: 1.48 },
  };
  const enhancerFactors = {
    waifu2x: 1.12,
    "realesrgan-anime": 1.2,
    opencv: 1.04,
  };

  const profile = outputProfiles[outputFormat] || { base: 0.95, variance: 0.18 };
  const inputFactor = inputFactors[String(source?.format || "").toLowerCase()] || 0.9;
  const imageFormat = String(options?.imageFormat || "jpg").toLowerCase();
  const qualityMode = String(options?.qualityMode || "quality_auto").toLowerCase();
  const imageFactor = imageFactors[imageFormat]?.[qualityMode] ?? 0.92;
  const enhancerFactor = enhancerFactors[options?.enhancer] ?? 1.08;
  const deviceFactor = Number(options?.deviceMultiplier || 1);
  const selectedCount = Number(options?.selectedCount || 1);
  const batchFactor = selectedCount > 1 ? 0.96 : 1;

  const estimate = baseSize * profile.base * inputFactor * imageFactor * enhancerFactor * deviceFactor * batchFactor;
  const low = Math.max(1, estimate * (1 - profile.variance));
  const high = Math.max(low + 1, estimate * (1 + profile.variance));
  return {
    low: Number(low.toFixed(1)),
    high: Number(high.toFixed(1)),
  };
}

function sumEstimateRanges(sources, outputFormat, options) {
  return sources.reduce(
    (acc, source) => {
      const range = estimateOutputRangeMb(source, outputFormat, options);
      return {
        low: acc.low + range.low,
        high: acc.high + range.high,
      };
    },
    { low: 0, high: 0 },
  );
}

function formatEstimateRange(range) {
  if (!range || !(range.low > 0) || !(range.high > 0)) return "-";
  const spread = Math.abs(range.high - range.low);
  if (spread < 8) return `约 ${formatSize((range.low + range.high) / 2)}`;
  return `${formatSize(range.low)} - ${formatSize(range.high)}`;
}

function naturalSortKey(value) {
  return String(value || "")
    .replace(/\\/g, "/")
    .split(/(\d+(?:\.\d+)?)/)
    .filter(Boolean)
    .flatMap((chunk) => {
      if (!/^\d+(?:\.\d+)?$/.test(chunk)) return [chunk.toLowerCase()];
      return chunk.includes(".") ? chunk.split(".").map((part) => Number(part)) : [Number(chunk)];
    });
}

function compareNatural(left, right) {
  const leftKey = naturalSortKey(left);
  const rightKey = naturalSortKey(right);
  const maxLength = Math.max(leftKey.length, rightKey.length);
  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftKey[index];
    const rightPart = rightKey[index];
    if (leftPart === rightPart) continue;
    if (leftPart == null) return -1;
    if (rightPart == null) return 1;
    if (typeof leftPart === "number" && typeof rightPart === "number") return leftPart - rightPart;
    return String(leftPart).localeCompare(String(rightPart), "zh-Hans-CN", { numeric: true, sensitivity: "base" });
  }
  return 0;
}

function sortEnhancerModels(models) {
  const order = {
    waifu2x: 0,
    "realesrgan-anime": 1,
    opencv: 9,
  };
  return [...(models || [])].sort((left, right) => {
    const leftRank = order[left?.name] ?? 5;
    const rightRank = order[right?.name] ?? 5;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 5v5h-5M4 19v-5h5m10.4-1A7 7 0 0 0 7 6.8M4.6 11A7 7 0 0 0 17 17.2" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function ChevronIcon({ collapsed }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={collapsed ? "m9 6 6 6-6 6" : "m6 9 6 6 6-6"} />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

function ModelGlyph({ name }) {
  if (name === "waifu2x") {
    return (
      <div className="model-glyph glyph-waifu" aria-hidden="true">
        <span className="glyph-dot dot-a" />
        <span className="glyph-dot dot-b" />
        <span className="glyph-dot dot-c" />
        <span className="glyph-dot dot-d" />
      </div>
    );
  }

  if (name === "opencv") {
    return (
      <div className="model-glyph glyph-opencv" aria-hidden="true">
        <span className="glyph-frame" />
      </div>
    );
  }

  return (
    <div className="model-glyph glyph-realesrgan" aria-hidden="true">
      <span className="glyph-spark spark-a" />
      <span className="glyph-spark spark-b" />
      <span className="glyph-spark spark-c" />
    </div>
  );
}

function CompareSlider({ beforeSrc, afterSrc, beforeLabel = "\u539f\u56fe", afterLabel = "\u63d0\u5347\u540e", value, onChange, loading, emptyText }) {
  const stageRef = useRef(null);
  const dragStateRef = useRef({ active: false, x: 0, y: 0, pointerId: null });
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const safeValue = Math.min(100, Math.max(0, Number(value || 50)));
  const hasPreview = Boolean(beforeSrc || afterSrc);

  const clampOffset = (nextZoom, nextOffset) => {
    const stage = stageRef.current;
    if (!stage) return nextOffset;
    const maxX = Math.max(0, ((nextZoom - 1) * stage.clientWidth) / 2);
    const maxY = Math.max(0, ((nextZoom - 1) * stage.clientHeight) / 2);
    return {
      x: Math.min(maxX, Math.max(-maxX, nextOffset.x)),
      y: Math.min(maxY, Math.max(-maxY, nextOffset.y)),
    };
  };
  const commitZoom = (nextZoom) => {
    const safeZoom = Math.min(4, Math.max(1, Number(nextZoom) || 1));
    setZoom(safeZoom);
    setOffset((current) => clampOffset(safeZoom, current));
  };

  useEffect(() => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    dragStateRef.current = { active: false, x: 0, y: 0, pointerId: null };
  }, [beforeSrc, afterSrc]);

  useEffect(() => {
    const handleResize = () => {
      setOffset((current) => clampOffset(zoom, current));
    };
    if (typeof window === "undefined") return undefined;
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [zoom]);

  const handleZoomIn = () => commitZoom(zoom + 0.25);
  const handleZoomOut = () => commitZoom(zoom - 0.25);
  const handleResetView = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  };
  const handleWheel = (event) => {
    event.preventDefault();
    commitZoom(zoom + (event.deltaY < 0 ? 0.2 : -0.2));
  };
  const handlePointerDown = (event) => {
    if (zoom <= 1) return;
    dragStateRef.current = {
      active: true,
      x: event.clientX,
      y: event.clientY,
      pointerId: event.pointerId,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const handlePointerMove = (event) => {
    if (!dragStateRef.current.active || zoom <= 1) return;
    const deltaX = event.clientX - dragStateRef.current.x;
    const deltaY = event.clientY - dragStateRef.current.y;
    dragStateRef.current = { ...dragStateRef.current, x: event.clientX, y: event.clientY };
    setOffset((current) => clampOffset(zoom, { x: current.x + deltaX, y: current.y + deltaY }));
  };
  const handlePointerUp = (event) => {
    if (dragStateRef.current.pointerId != null) {
      event.currentTarget.releasePointerCapture?.(dragStateRef.current.pointerId);
    }
    dragStateRef.current = { active: false, x: 0, y: 0, pointerId: null };
  };

  return (
    <div className={`compare-shell ${loading ? "is-loading" : ""}`}>
      {hasPreview ? (
        <div className="compare-toolbar">
          <div className="compare-zoom-group">
            <button type="button" className="compare-tool-btn" onClick={handleZoomOut} disabled={zoom <= 1} aria-label="\u7f29\u5c0f\u9884\u89c8">
              -
            </button>
            <span className="compare-zoom-readout">{Math.round(zoom * 100)}%</span>
            <button type="button" className="compare-tool-btn" onClick={handleZoomIn} disabled={zoom >= 4} aria-label="\u653e\u5927\u9884\u89c8">
              +
            </button>
            <button type="button" className="compare-tool-btn wide" onClick={handleResetView}>
              {"\u91cd\u7f6e\u89c6\u56fe"}
            </button>
          </div>
          <span className="compare-toolbar-note">{"\u6eda\u8f6e\u7f29\u653e\uff0c\u653e\u5927\u540e\u53ef\u62d6\u62fd\u540c\u6b65\u5e73\u79fb\u3002"}</span>
        </div>
      ) : null}
      {hasPreview ? (
        <div
          ref={stageRef}
          className={`compare-stage ${zoom > 1 ? "is-draggable" : ""}`}
          onWheel={handleWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <div className="compare-media" style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}>
            {beforeSrc ? <img className="compare-image" src={beforeSrc} alt={beforeLabel} draggable="false" /> : null}
            {afterSrc ? (
              <div className="compare-overlay" style={{ clipPath: `inset(0 0 0 ${safeValue}%)` }}>
                <img className="compare-image" src={afterSrc} alt={afterLabel} draggable="false" />
              </div>
            ) : null}
          </div>
          <div className="compare-divider" style={{ left: `${safeValue}%` }}>
            <span className="compare-handle" aria-hidden="true">&lt;&gt;</span>
          </div>
          <div className="compare-badge before">{beforeLabel}</div>
          <div className="compare-badge after">{afterLabel}</div>
          {loading ? <div className="compare-loading">Loading preview...</div> : null}
        </div>
      ) : (
        <div className="compare-empty">{emptyText || "\u5f53\u524d\u7d20\u6750\u8fd8\u6ca1\u6709\u53ef\u7528\u9884\u89c8\u3002"}</div>
      )}
      {hasPreview ? (
        <input
          className="compare-range"
          type="range"
          min="0"
          max="100"
          value={safeValue}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label="\u8c03\u6574\u524d\u540e\u5bf9\u6bd4\u4f4d\u7f6e"
        />
      ) : null}
    </div>
  );
}

function HeroPanel({ title, text, onRefresh, primaryAction }) {
  return (
    <section className="hero-panel">
      <div className="hero-copy">
        <p className="panel-kicker">漫画画质提升</p>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      <div className="hero-actions">
        <button type="button" className="ui-btn secondary icon-btn" onClick={onRefresh}>
          <RefreshIcon />
          刷新数据
        </button>
        {primaryAction ? (
          <button type="button" className={`ui-btn ${primaryAction.kind || "primary"}`} onClick={primaryAction.onClick}>
            {primaryAction.label}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function SidebarModules({ activePage, isCollapsed, onToggleCollapse, onSelect }) {
  return (
    <section className="sidebar-card group-card">
      <button type="button" className="group-head" onClick={onToggleCollapse} aria-expanded={!isCollapsed}>
        <div className="group-head-copy">
          <p className="sidebar-heading">功能模块</p>
          <span className="sidebar-text">收起子页面</span>
        </div>
      </button>
      {!isCollapsed ? (
        <div className="module-list">
          <button type="button" className={`module-item ${activePage === "split" ? "is-active" : ""}`} onClick={() => onSelect("split")}>
            <strong>拆图模块</strong>
            <span>漫画文件拆包</span>
          </button>
          <button type="button" className={`module-item ${activePage === "enhance" ? "is-active" : ""}`} onClick={() => onSelect("enhance")}>
            <strong>画质提升</strong>
            <span>AI 超分辨率增强</span>
          </button>
          <button type="button" className={`module-item ${activePage === "export" ? "is-active" : ""}`} onClick={() => onSelect("export")}>
            <strong>导出模块</strong>
            <span>多格式转换与导出</span>
          </button>
        </div>
      ) : null}
    </section>
  );
}

function SourcePool({
  sources,
  selectedSources,
  onToggle,
  onSelectAll,
  onClearSelection,
  onSwitchDir,
  onImportDir,
  onOpenRoot,
}) {
  return (
    <section className="surface-panel pool-panel">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">素材池</p>
          <h2>当前素材池</h2>
        </div>
        <span className="badge">{sources.length} 项</span>
      </div>
      <div className="pool-actions">
        <button type="button" className="ui-btn secondary" onClick={onSwitchDir}>
          切换素材目录
        </button>
        <button type="button" className="ui-btn secondary" onClick={onImportDir}>
          导入目录
        </button>
        <button type="button" className="ui-btn secondary" onClick={onSelectAll}>
          全选当前目录
        </button>
        <button type="button" className="ui-btn secondary" onClick={onClearSelection}>
          清空选择
        </button>
        <button type="button" className="ui-btn secondary pool-open-btn" onClick={onOpenRoot}>
          打开素材池
        </button>
      </div>
      <div className="pool-list">
        {sources.length ? (
          sources.map((source) => {
            const selected = selectedSources.includes(source.name);
            return (
              <button key={source.name} type="button" className={`pool-item ${selected ? "is-active" : ""}`} onClick={() => onToggle(source.name)}>
                <div className="pool-check">{selected ? "✓" : ""}</div>
                <div className="pool-copy">
                  <strong>{source.name}</strong>
                  {selected ? <em>当前选择</em> : null}
                  <span>{`${formatSourceType(source.format)} · ${formatSize(source.size_mb)}`}</span>
                </div>
              </button>
            );
          })
        ) : (
          <div className="empty-card">当前没有素材，先导入文件或图片目录。</div>
        )}
      </div>
    </section>
  );
}

function ImportWorkspace({ content, isDragActive, onDragState, onDropFile, onImportFile, onImportDir, onSwitchDir, sourcePool }) {
  return (
    <div className="content-grid">
      <section className="surface-panel import-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">{content.kicker}</p>
            <h2>{content.cardTitle}</h2>
          </div>
          <span className="badge soft">不改动原文件</span>
        </div>
        <div
          className={`drop-zone ${isDragActive ? "is-dragging" : ""}`}
          onClick={onImportFile}
          onDragEnter={(event) => {
            event.preventDefault();
            onDragState(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            onDragState(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            onDragState(false);
          }}
          onDrop={onDropFile}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onImportFile();
            }
          }}
        >
          <div className="drop-mark">
            <PlusIcon />
          </div>
          <strong>{content.cardText}</strong>
          <p>{content.cardHint}</p>
        </div>
        <div className="import-footer-actions">
          <button type="button" className="ui-btn secondary" onClick={onImportFile}>
            导入文件
          </button>
          <button type="button" className="ui-btn secondary" onClick={onImportDir}>
            导入目录
          </button>
          <button type="button" className="ui-btn secondary" onClick={onSwitchDir}>
            切换素材目录
          </button>
        </div>
      </section>
      {sourcePool}
    </div>
  );
}

function ActionWorkspace({ content, actionLabel, onRun, sourcePool }) {
  const steps = ["从右侧素材池选择一个或多个素材", content.cardText, content.cardHint];

  return (
    <div className="content-grid">
      <section className="surface-panel workflow-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">{content.kicker}</p>
            <h2>{content.cardTitle}</h2>
          </div>
          <span className="badge soft">单模块执行</span>
        </div>
        <div className="workflow-stack">
          <div className="workflow-note">
            <strong>当前模块说明</strong>
            <p>{content.cardText}</p>
          </div>
          <div className="workflow-steps">
            {steps.map((step, index) => (
              <div key={step} className="workflow-step">
                <div className="workflow-index">{index + 1}</div>
                <div>{step}</div>
              </div>
            ))}
          </div>
          <div className="workflow-action-card">
            <div>
              <strong>{actionLabel}</strong>
              <p>确认选中素材后，开始执行当前模块。</p>
            </div>
            <button type="button" className="ui-btn primary" onClick={onRun}>
              {actionLabel}
            </button>
          </div>
        </div>
      </section>
      {sourcePool}
    </div>
  );
}

function EnhanceWorkspace({
  content,
  sourceRoot,
  outputPath,
  selectedSourceItems,
  enhancerModels,
  selectedEnhancer,
  onSelectEnhancer,
  selectedImageFormat,
  selectedPdfQualityMode,
  selectedWaifuNoise,
  onSelectWaifuNoise,
  onSwitchDir,
  onPickOutputPath,
  onRun,
  previewPair,
  previewLoading,
  compareValue,
  onCompareChange,
  sourcePool,
}) {
  const selectedLabel = selectedSourceItems.length
    ? selectedSourceItems.length === 1
      ? selectedSourceItems[0].name
      : `已选 ${selectedSourceItems.length} 项素材`
    : "尚未选择素材";
  const previewNote = previewPair?.after_url
    ? "右侧优先展示当前素材最近一次提升结果的前后对比。"
    : "当前还没有已生成的 pages_ai 预览，执行提升后这里会自动更新。";

  return (
    <div className="content-grid enhance-layout">
      <section className="surface-panel enhance-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">{content.kicker}</p>
            <h2>{content.cardTitle}</h2>
          </div>
          <span className="badge soft">单模块执行</span>
        </div>

        <div className="enhance-stack">
          <section className="enhance-info-card">
            <strong>当前模块说明</strong>
            <p>{content.cardText}</p>
            <p>{content.cardHint}</p>
          </section>

          <section className="enhance-control-card">
            <div className="enhance-control-head">
              <strong>目录快捷入口</strong>
              <span>提升页里直接切换素材目录和导出目录，不用再跳设置页。</span>
            </div>
            <div className="enhance-action-grid">
              <button type="button" className="ui-btn secondary" onClick={onSwitchDir}>
                {"\u5207\u6362\u7d20\u6750\u76ee\u5f55"}
              </button>
              <button type="button" className="ui-btn secondary" onClick={onPickOutputPath}>
                {"\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55"}
              </button>
            </div>
            <div className="enhance-path-list">
              <div className="path-field">
                <strong>当前素材池</strong>
                <span title={sourceRoot || ""}>{sourceRoot || "\u672a\u8bbe\u7f6e\u7d20\u6750\u76ee\u5f55"}</span>
              </div>
              <div className="path-field">
                <strong>当前导出目录</strong>
                <span title={outputPath || ""}>{outputPath || "\u7cfb\u7edf\u9ed8\u8ba4\u8f93\u51fa\u76ee\u5f55"}</span>
              </div>
            </div>
          </section>

          <section className="enhance-model-section">
            <div className="enhance-settings-head">
              <strong>提升模型</strong>
              <span>在提升页直接切模型和降噪，不用再跳去设置页。</span>
            </div>
            <div className="model-grid model-grid--compact enhance-model-grid">
              {enhancerModels.map((model) => (
                <button
                  key={model.name}
                  type="button"
                  className={`model-card ${selectedEnhancer === model.name ? "is-active" : ""}`}
                  onClick={() => onSelectEnhancer(model.name)}
                >
                  <div className={`model-mark ${model.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}>
                    <ModelGlyph name={model.name} />
                  </div>
                  <div className="model-top">
                    <strong>{enhancerMeta[model.name]?.title || model.name}</strong>
                    {model.recommended ? <span className="model-badge">推荐</span> : null}
                  </div>
                  <div className="model-copy">
                    <span>{enhancerMeta[model.name]?.description || "用于当前素材的增强模型。"}</span>
                    <span>{model.available ? "当前可用" : "当前不可用"}</span>
                  </div>
                </button>
              ))}
            </div>
            {selectedEnhancer === "waifu2x" ? (
              <div className="enhance-inline-section">
                <strong>waifu2x 降噪等级</strong>
                <div className="format-pills">
                  {waifuNoiseOptions.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={`pill-btn ${selectedWaifuNoise === item.value ? "is-active" : ""}`}
                      onClick={() => onSelectWaifuNoise(item.value)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <section className="enhance-summary-grid">
            <div className="summary-card">
              <h3>当前素材</h3>
              <p>{selectedLabel}</p>
            </div>
            <div className="summary-card">
              <h3>增强模型</h3>
              <p>{enhancerMeta[selectedEnhancer]?.title || selectedEnhancer}</p>
            </div>
            <div className="summary-card">
              <h3>输出图格式</h3>
              <p>{String(selectedImageFormat || "jpg").toUpperCase()}</p>
            </div>
            <div className="summary-card">
              <h3>压缩质量</h3>
              <p>{pdfQualityOptions.find((item) => item.value === selectedPdfQualityMode)?.label || selectedPdfQualityMode}</p>
            </div>
          </section>

          <div className="workflow-action-card">
            <div>
              <strong>执行提升</strong>
              <p>确认素材后开始执行当前模块，右侧对比会在刷新后优先展示最新提升结果。</p>
            </div>
            <button type="button" className="ui-btn primary" onClick={onRun}>
              执行提升
            </button>
          </div>
        </div>
      </section>

      <section className="surface-panel enhance-preview-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">提升效果对比</p>
            <h2>拖动查看前后差异</h2>
          </div>
          <span className="badge">{previewPair?.after_url ? "已就绪" : "等待结果"}</span>
        </div>
        <CompareSlider
          beforeSrc={previewPair?.before_url}
          afterSrc={previewPair?.after_url || previewPair?.before_url}
          beforeLabel="原图"
          afterLabel={previewPair?.after_url ? "提升后" : "待生成"}
          value={compareValue}
          onChange={onCompareChange}
          loading={previewLoading}
          emptyText="当前素材还没有可用预览。先选择图片目录，或者先跑一次提升任务。"
        />
        <div className="enhance-preview-copy">
          <strong>预览来源</strong>
          <p>{previewPair?.source_name || selectedLabel}</p>
          <p>{previewNote}</p>
        </div>
      </section>
      <div className="enhance-pool-span">{sourcePool}</div>
    </div>
  );
}

function ExportWorkspace({
  content,
  selectedSourceLabel,
  outputPath,
  outputDevice,
  onOutputDeviceChange,
  mergeOutputEnabled,
  onToggleMergeOutput,
  onPickOutputPath,
  onOpenOutputPath,
  formatCards,
  onToggleFormat,
  onRunExport,
  onRunFull,
  sourcePool,
}) {
  const selectedCount = formatCards.filter((item) => item.selected).length;

  return (
    <div className="content-grid export-layout">
      <section className="surface-panel export-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">{content.kicker}</p>
            <h2>{content.cardTitle}</h2>
          </div>
          <span className="badge soft export-tag">{selectedSourceLabel}</span>
        </div>

        <section className="export-row-block">
          <label className="field-label">输出目录</label>
          <div className="path-row">
            <div className="path-box large">{outputPath || "系统默认输出目录"}</div>
            <button type="button" className="ui-btn secondary" onClick={onPickOutputPath}>
              选择目录
            </button>
            <button type="button" className="ui-btn secondary" onClick={onOpenOutputPath}>
              打开目录
            </button>
          </div>
        </section>

        <section className="export-row-block">
          <label className="field-label">目标设备</label>
          <select className="device-select" value={outputDevice} onChange={(event) => onOutputDeviceChange(event.target.value)}>
            {deviceOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </section>

        <section className="export-row-block">
          <label className="field-label">合并输出策略</label>
          <div className="toggle-card-row">
            <label className="toggle-card">
              <input type="checkbox" checked={mergeOutputEnabled} onChange={(event) => onToggleMergeOutput(event.target.checked)} />
              <span>多选素材时合并输出为单文件</span>
            </label>
          </div>
        </section>

        <div className="summary-grid">
          <section className="summary-card">
            <h3>导出位置</h3>
            <p>{outputPath || "系统默认输出目录"}</p>
          </section>
          <section className="summary-card">
            <h3>当前预估</h3>
            <p>{selectedCount ? `已选 ${selectedCount} 种格式` : "请先选择导出格式"}</p>
          </section>
          <section className="summary-card span-2">
            <h3>导出结构</h3>
            <p>{`每本输出到独立目录，示例：${outputPath || "系统默认输出目录"}\\${baseName(selectedSourceLabel)}`}</p>
          </section>
        </div>

        <div className="action-bar export-action-bar">
          <button type="button" className="ui-btn primary subtle" onClick={onRunExport}>
            只执行导出
          </button>
          <button type="button" className="ui-btn accent-wide" onClick={onRunFull}>
            一键全部完成
          </button>
        </div>

        <div className="format-card-list format-card-list--long">
          {formatCards.map((item) => (
            <button key={item.key} type="button" className={`format-card ${item.selected ? "is-active" : ""}`} onClick={() => onToggleFormat(item.key)}>
              <div className="format-card-head">
                <label className="format-check">
                  <input
                    type="checkbox"
                    checked={item.selected}
                    onChange={() => onToggleFormat(item.key)}
                    onClick={(event) => event.stopPropagation()}
                  />
                  <span>{item.label}</span>
                </label>
                <strong>{item.sizeText}</strong>
              </div>
              <p>{item.description}</p>
              <em>适合：{item.fit}</em>
            </button>
          ))}
        </div>
      </section>
      {sourcePool}
    </div>
  );
}

function SettingsWorkspace({
  keepOriginalPages,
  keepEnhancedPages,
  onToggleOriginal,
  onToggleEnhanced,
  selectedImageFormat,
  onSelectImageFormat,
  selectedPdfQualityMode,
  onSelectPdfQualityMode,
  enhancerModels,
  selectedEnhancer,
  onSelectEnhancer,
  selectedWaifuNoise,
  onSelectWaifuNoise,
  mergeOutputEnabled,
  onToggleMergeOutput,
  outputPath,
  onPickOutputPath,
  onOpenOutputPath,
  onResetOutputPath,
  selectedFormats,
  outputFormats,
  onToggleFormat,
  formatCards,
  estimatedSourceSize,
  onRunFull,
  sourcePool,
}) {
  return (
    <div className="content-grid settings-layout">
      <section className="surface-panel settings-workspace">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">执行设置</p>
            <h2>默认执行策略</h2>
          </div>
        </div>

        <section className="setting-section">
          <h3>图片保留策略</h3>
          <div className="toggle-card-row">
            <label className="toggle-card">
              <input type="checkbox" checked={keepOriginalPages} onChange={(event) => onToggleOriginal(event.target.checked)} />
              <span>保留 pages 原图</span>
            </label>
            <label className="toggle-card">
              <input type="checkbox" checked={keepEnhancedPages} onChange={(event) => onToggleEnhanced(event.target.checked)} />
              <span>保留 pages_ai 增强图</span>
            </label>
          </div>
        </section>

        <section className="setting-section">
          <h3>合并输出策略</h3>
          <p className="setting-copy">多选素材时，一键全部运行会先合并、再优化、最后导出成一个文件；关闭时按每项素材分别处理。</p>
          <div className="toggle-card-row">
            <label className="toggle-card">
              <input type="checkbox" checked={mergeOutputEnabled} onChange={(event) => onToggleMergeOutput(event.target.checked)} />
              <span>多选素材时合并输出为单文件</span>
            </label>
          </div>
        </section>

        <section className="setting-section">
          <h3>拆图图片格式</h3>
          <p className="setting-copy">控制 PDF 拆图和后续 pages / pages_ai 的图片格式。漫画线稿建议优先试 PNG 或 WEBP。</p>
          <div className="format-pills">
            {imageFormatOptions.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`pill-btn ${selectedImageFormat === item.value ? "is-active" : ""}`}
                onClick={() => onSelectImageFormat(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>

        <section className="setting-section">
          <h3>图片压缩质量</h3>
          <p className="setting-copy">对 JPG / WEBP 生效。PNG 仍保持无损，主要用于在体积和细节之间取平衡。</p>
          <div className="model-grid model-grid--compact">
            {pdfQualityOptions.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`model-card ${selectedPdfQualityMode === item.value ? "is-active" : ""}`}
                onClick={() => onSelectPdfQualityMode(item.value)}
              >
                <div className="model-top">
                  <strong>{item.label}</strong>
                </div>
                <div className="model-copy">
                  <span>{item.hint}</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="setting-section">
          <h3>画质提升模型</h3>
          <p className="setting-copy">选择增强引擎。优先展示可用模型，推荐 AI 模型，OpenCV 作为兼容兜底。</p>
          <div className="model-grid model-grid--compact">
            {enhancerModels.map((model) => (
              <button
                key={model.name}
                type="button"
                className={`model-card ${selectedEnhancer === model.name ? "is-active" : ""}`}
                onClick={() => onSelectEnhancer(model.name)}
              >
                <div className={`model-mark ${model.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}>
                  <ModelGlyph name={model.name} />
                </div>
                <div className="model-top">
                  <strong>{enhancerMeta[model.name]?.title || model.name}</strong>
                  {model.recommended ? <span className="model-badge">推荐</span> : null}
                </div>
                <div className="model-copy">
                  <span>{enhancerMeta[model.name]?.description || "可用于当前环境的增强模型。"}</span>
                  <span>{model.available ? "当前可用" : "当前不可用"}</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        {selectedEnhancer === "waifu2x" ? (
          <section className="setting-section">
            <h3>waifu2x 降噪等级</h3>
            <p className="setting-copy">线稿发虚时先试 0 或关闭；扫描噪点较重时再提高到 1 或 2。</p>
            <div className="format-pills">
              {waifuNoiseOptions.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={`pill-btn ${selectedWaifuNoise === item.value ? "is-active" : ""}`}
                  onClick={() => onSelectWaifuNoise(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <section className="setting-section">
          <h3>导出地址</h3>
          <p className="setting-copy">指定所有任务的默认输出目录，不设置时使用系统默认。</p>
          <div className="directory-actions">
            <button type="button" className="ui-btn secondary" onClick={onPickOutputPath}>
              选择导出目录
            </button>
            <button type="button" className="ui-btn secondary" onClick={onOpenOutputPath}>
              打开目录
            </button>
            <button type="button" className="ui-btn secondary" onClick={onResetOutputPath}>
              清除
            </button>
          </div>
          <div className="path-field">{outputPath || "系统默认输出目录"}</div>
        </section>

        <section className="setting-section">
          <h3>完整执行</h3>
          <p className="setting-copy">按当前勾选素材运行拆图、增强与导出；未勾选时使用当前选择。</p>
          <button type="button" className="ui-btn accent-bar" onClick={onRunFull}>
            一键全部运行
          </button>
        </section>

        <section className="setting-section">
          <h3>预计导出体积</h3>
          <p className="setting-copy">
            {estimatedSourceSize > 0 ? `按当前素材 ${formatSize(estimatedSourceSize)} 原始大小估算` : "请先选择素材以估算导出体积"}
          </p>
        </section>

        <section className="setting-section">
          <h3>导出文件模型选择</h3>
          <p className="setting-copy">下面的格式卡与导出页保持一致，在执行设置页也可以直接决定最终输出。</p>
          <div className="format-card-list format-card-list--long compact">
            {formatCards.map((item) => (
              <button key={item.key} type="button" className={`format-card ${item.selected ? "is-active" : ""}`} onClick={() => onToggleFormat(item.key)}>
                <div className="format-card-head">
                  <label className="format-check">
                    <input
                      type="checkbox"
                      checked={item.selected}
                      onChange={() => onToggleFormat(item.key)}
                      onClick={(event) => event.stopPropagation()}
                    />
                    <span>{item.label}</span>
                  </label>
                  <strong>{item.sizeText}</strong>
                </div>
                <p>{item.description}</p>
                <em>适合：{item.fit}</em>
              </button>
            ))}
          </div>
        </section>
      </section>
      {sourcePool}
    </div>
  );
}

function TaskWorkspace({ jobs, currentJob, detailMode, taskPage, totalTaskPages, onTaskPageChange, onSelectJob, onDeleteJob, onBack, onOpenWorkspace, onOpenOutput }) {
  if (!detailMode) {
    const pagedJobs = jobs.slice((taskPage - 1) * 10, taskPage * 10);
    return (
      <section className="surface-panel task-list-panel single">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">历史任务列表</p>
            <h2>任务结果</h2>
          </div>
          <span className="badge">{jobs.length} 项</span>
        </div>
        <div className="task-list">
          {jobs.length ? (
            pagedJobs.map((job) => (
              <div
                key={job.id}
                className="task-row"
                role="button"
                tabIndex={0}
                onClick={() => onSelectJob(job.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectJob(job.id);
                  }
                }}
              >
                <div className="task-main">
                  <strong>{job.name}</strong>
                  <span>{job.source_name}</span>
                </div>
                <span className={`task-status-chip is-${job.status || "idle"}`}>{formatStatus(job.status)}</span>
                <div className="task-stage">{formatStage(job.stage)}</div>
                <div className="task-progress-block">
                  <div className="task-progress-top">
                    <span>{job.progress_label || formatStatus(job.status)}</span>
                    <strong>{`${Number(job.progress || 0)}%`}</strong>
                  </div>
                  <div className="task-progress-bar">
                    <div className="task-progress-fill" style={{ width: `${Number(job.progress || 0)}%` }} />
                  </div>
                </div>
                <button
                  type="button"
                  className="task-delete-btn"
                  aria-label={`删除任务 ${job.name}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteJob(job.id);
                  }}
                >
                  <CloseIcon />
                </button>
              </div>
            ))
          ) : (
            <div className="empty-card">当前还没有任务结果。</div>
          )}
        </div>
        {totalTaskPages > 1 ? (
          <div className="task-pagination">
            <button type="button" className="ui-btn secondary" disabled={taskPage <= 1} onClick={() => onTaskPageChange(taskPage - 1)}>
              上一页
            </button>
            <span className="task-pagination-info">{taskPage} / {totalTaskPages}</span>
            <button type="button" className="ui-btn secondary" disabled={taskPage >= totalTaskPages} onClick={() => onTaskPageChange(taskPage + 1)}>
              下一页
            </button>
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className="surface-panel task-detail-panel single">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">任务详情</p>
          <h2>{currentJob?.name || "任务详情"}</h2>
        </div>
        <div className="hero-actions">
          <button type="button" className="ui-btn secondary" onClick={onBack}>
            返回列表
          </button>
          {currentJob ? <span className={`task-status-chip is-${currentJob.status || "idle"}`}>{formatStatus(currentJob.status)}</span> : null}
        </div>
      </div>

      {currentJob ? (
        <>
          <section className="detail-progress-card">
            <div className="task-progress-top">
              <span>当前进度</span>
              <strong>{`${Number(currentJob.progress || 0)}%`}</strong>
            </div>
            <div className="task-progress-bar">
              <div className="task-progress-fill" style={{ width: `${Number(currentJob.progress || 0)}%` }} />
            </div>
          </section>

          <div className="directory-actions">
            <button type="button" className="ui-btn secondary" onClick={onOpenWorkspace}>
              打开工作目录
            </button>
            <button type="button" className="ui-btn secondary" onClick={onOpenOutput}>
              打开输出目录
            </button>
          </div>

          <div className="task-detail-grid">
            <section className="summary-card">
              <h3>输出文件</h3>
              {currentJob.outputs?.length ? currentJob.outputs.map((item) => <p key={item}>{baseName(item)}</p>) : <p>暂无输出</p>}
            </section>
            <section className="summary-card">
              <h3>任务说明</h3>
              <p>{`阶段：${formatStage(currentJob.stage)}`}</p>
              <p>{currentJob.progress_label || "-"}</p>
              <p>{`输出目录：${currentJob.output_dir || "-"}`}</p>
              {currentJob.error_detail ? <p>{currentJob.error_detail.split("\n")[0]}</p> : null}
            </section>
          </div>

          <section className="task-log-panel">
            <h3>任务日志</h3>
            <div className="task-log-list">
              {(currentJob.logs?.length ? currentJob.logs : currentJob.notes || ["暂无日志"]).map((line, index) => (
                <div key={`${currentJob.id}-${index}`} className="task-log-line">
                  {line}
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <div className="empty-card">没有可显示的任务详情。</div>
      )}
    </section>
  );
}

export default function App() {
  const [data, setData] = useState(fallbackData);
  const [activePage, setActivePage] = useState(() => readPageFromHash());
  const [isFunctionGroupCollapsed, setIsFunctionGroupCollapsed] = useState(false);
  const [selectedSources, setSelectedSources] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [taskPage, setTaskPage] = useState(1);
  const [selectedFormats, setSelectedFormats] = useState(() => readStoredValue("formats", ["cbz", "pdf"]));
  const [keepOriginalPages, setKeepOriginalPages] = useState(() => readStoredValue("keep-original", true));
  const [keepEnhancedPages, setKeepEnhancedPages] = useState(() => readStoredValue("keep-enhanced", true));
  const [selectedImageFormat, setSelectedImageFormat] = useState(() => readStoredValue("image-format", "jpg"));
  const [selectedPdfQualityMode, setSelectedPdfQualityMode] = useState(() => readStoredValue("pdf-quality-mode", "fast_auto"));
  const [outputDevice, setOutputDevice] = useState(() => readStoredValue("output-device", "android-tablet"));
  const [selectedEnhancer, setSelectedEnhancer] = useState(() => readStoredValue("enhancer", "waifu2x"));
  const [selectedWaifuNoise, setSelectedWaifuNoise] = useState(() => readStoredValue("waifu-noise", 0));
  const [mergeOutputEnabled, setMergeOutputEnabled] = useState(() => readStoredValue("merge-output-enabled", false));
  const [enhancerModels, setEnhancerModels] = useState(sortEnhancerModels([
    { name: "waifu2x", available: true, recommended: true },
    { name: "realesrgan-anime", available: true, recommended: false },
  ]));
  const [isTaskDetailOpen, setIsTaskDetailOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [isDragActive, setIsDragActive] = useState(false);
  const [enhancePreview, setEnhancePreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [compareValue, setCompareValue] = useState(50);
  const fileInputRef = useRef(null);

  useEffect(() => writeStoredValue("formats", selectedFormats), [selectedFormats]);
  useEffect(() => writeStoredValue("keep-original", keepOriginalPages), [keepOriginalPages]);
  useEffect(() => writeStoredValue("keep-enhanced", keepEnhancedPages), [keepEnhancedPages]);
  useEffect(() => writeStoredValue("image-format", selectedImageFormat), [selectedImageFormat]);
  useEffect(() => writeStoredValue("pdf-quality-mode", selectedPdfQualityMode), [selectedPdfQualityMode]);
  useEffect(() => writeStoredValue("output-device", outputDevice), [outputDevice]);
  useEffect(() => writeStoredValue("enhancer", selectedEnhancer), [selectedEnhancer]);
  useEffect(() => writeStoredValue("waifu-noise", selectedWaifuNoise), [selectedWaifuNoise]);
  useEffect(() => writeStoredValue("merge-output-enabled", mergeOutputEnabled), [mergeOutputEnabled]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const syncFromHash = () => {
      const page = readPageFromHash();
      setActivePage((current) => (current === page ? current : page));
    };
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const nextHash = `#${activePage}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
    }
  }, [activePage]);

  const exportFormatOptions = useMemo(() => {
    if (!(Array.isArray(data.export_options) && data.export_options.length)) {
      return ["cbz", "zip", "epub", "mobi", "pdf"];
    }
    return data.export_options
      .map((item) => {
        if (typeof item === "string") return item.toLowerCase();
        const key = item?.key || item?.value || item?.name || item?.id || item?.format;
        return key ? String(key).toLowerCase() : null;
      })
      .filter(Boolean);
  }, [data.export_options]);

  const sortedSourceBooks = useMemo(
    () => [...(data.source_books || [])].sort((left, right) => compareNatural(left?.name, right?.name)),
    [data.source_books],
  );

  const selectedSourceItems = useMemo(
    () => selectedSources.map((name) => sortedSourceBooks.find((item) => item.name === name)).filter(Boolean),
    [sortedSourceBooks, selectedSources],
  );

  const currentJob = useMemo(
    () => data.jobs.find((item) => item.id === selectedJobId) || data.jobs[0] || null,
    [data.jobs, selectedJobId],
  );
  const totalTaskPages = useMemo(() => Math.max(1, Math.ceil((data.jobs?.length || 0) / 10)), [data.jobs]);

  useEffect(() => {
    if (taskPage > totalTaskPages) {
      setTaskPage(totalTaskPages);
    }
  }, [taskPage, totalTaskPages]);

  const previewSource = useMemo(() => selectedSourceItems[0] || sortedSourceBooks[0] || null, [selectedSourceItems, sortedSourceBooks]);
  const currentDevice = useMemo(() => deviceOptions.find((option) => option.value === outputDevice) || deviceOptions[0], [outputDevice]);

  const estimatedSourceSize = useMemo(() => {
    if (selectedSourceItems.length) {
      return selectedSourceItems.reduce((total, item) => total + Number(item.size_mb || 0), 0);
    }
    return Number(previewSource?.size_mb || 0);
  }, [selectedSourceItems, previewSource]);

  const estimateSources = useMemo(
    () => (selectedSourceItems.length ? selectedSourceItems : previewSource ? [previewSource] : []),
    [selectedSourceItems, previewSource],
  );

  const exportCards = useMemo(
    () =>
      exportFormatOptions.map((format) => {
        const meta = formatMeta[format] || {
          label: String(format).toUpperCase(),
          description: "导出为目标格式。",
          fit: "通用",
          ratio: 1.9,
        };
        return {
          key: format,
          ...meta,
          selected: selectedFormats.includes(format),
          sizeText: formatEstimateRange(
            sumEstimateRanges(estimateSources, format, {
              imageFormat: selectedImageFormat,
              qualityMode: selectedPdfQualityMode,
              enhancer: selectedEnhancer,
              deviceMultiplier: currentDevice.multiplier,
              selectedCount: estimateSources.length,
            }),
          ),
        };
      }),
    [exportFormatOptions, selectedFormats, estimateSources, selectedImageFormat, selectedPdfQualityMode, selectedEnhancer, currentDevice.multiplier],
  );

  const currentContent =
    activePage === "tasks" && isTaskDetailOpen
      ? { heroTitle: "任务详情", heroText: "查看输出文件、任务说明与日志。" }
      : pageContent[activePage] || pageContent.import;

  const loadDashboard = async () => {
    const response = await fetch("/api/dashboard");
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "读取数据失败");
    setData({
      ...fallbackData,
      ...payload,
      product_name: payload.product_name || fallbackData.product_name,
      tagline: payload.tagline || fallbackData.tagline,
    });
    setSelectedSources((current) => current.filter((name) => payload.source_books?.some((item) => item.name === name)));
    setSelectedJobId((current) => current || payload.jobs?.[0]?.id || "");
  };

  const upsertLocalJob = (job) => {
    if (!job?.id) return;
    setData((current) => {
      const nextJobs = [job, ...(current.jobs || []).filter((item) => item.id !== job.id)];
      return {
        ...current,
        jobs: nextJobs,
      };
    });
  };

  const loadModels = async () => {
    const response = await fetch("/api/models");
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "读取模型失败");
    const nextModels = Array.isArray(payload.models) && payload.models.length
      ? payload.models.filter((item) => item.name !== "opencv")
      : enhancerModels;
    setEnhancerModels(sortEnhancerModels(nextModels));
    if (!nextModels.some((item) => item.name === selectedEnhancer && item.available)) {
      const preferred = nextModels.find((item) => item.recommended && item.available) || nextModels.find((item) => item.available) || nextModels[0];
      if (preferred?.name) {
        setSelectedEnhancer(preferred.name);
      }
    }
  };

  useEffect(() => {
    loadDashboard().catch((error) => setMessage(error.message || "读取数据失败"));
    loadModels().catch(() => {});
    const timer = window.setInterval(() => {
      loadDashboard().catch(() => {});
    }, 2500);
    return () => window.clearInterval(timer);
  }, []);

  const loadEnhancePreview = async (sourceName) => {
    if (!sourceName) {
      setEnhancePreview(null);
      return;
    }
    setPreviewLoading(true);
    try {
      const params = new URLSearchParams({
        source_name: sourceName,
        enhancer: selectedEnhancer,
        waifu2x_noise: String(selectedWaifuNoise),
        image_format: selectedImageFormat,
      });
      const response = await fetch(`/api/enhance-preview?${params.toString()}`);
      const payload = await readJson(response);
      if (!response.ok) throw new Error(payload.error || "Failed to load preview");
      setEnhancePreview(payload.preview || null);
    } catch {
      setEnhancePreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  useEffect(() => {
    if (activePage !== "enhance") return;
    const sourceName = selectedSourceItems[0]?.name || previewSource?.name || "";
    loadEnhancePreview(sourceName).catch(() => {});
  }, [activePage, selectedSourceItems, previewSource, selectedEnhancer, selectedWaifuNoise, selectedImageFormat, data.jobs]);

  const pickDirectory = async (currentPath, title, options = {}) => {
    const response = await fetch("/api/pick-directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_path: currentPath, title, prefer_parent: currentPath === data.source_root, ...options }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "选择目录失败");
    return payload.path || "";
  };

  const openPath = async (path) => {
    if (!path) throw new Error("目录为空");
    const response = await fetch("/api/open-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "打开目录失败");
  };

  const updateConfig = async (payload) => {
    const response = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await readJson(response);
    if (!response.ok) throw new Error(result.error || "保存配置失败");
    return result;
  };

  const importFile = async (file) => {
    const formData = new FormData();
    formData.append("file", file, file.name);
    const response = await fetch("/api/import-file", { method: "POST", body: formData });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "导入文件失败");
    await loadDashboard();
    setSelectedSources([payload.file_name || file.name]);
    setMessage(`已导入：${payload.file_name || file.name}`);
  };

  const importFolder = async () => {
    const path = await pickDirectory(data.source_root, "选择素材目录");
    if (!path) return;
    const response = await fetch("/api/import-source-directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "导入目录失败");
    await loadDashboard();
    if (payload.folder_name) setSelectedSources([payload.folder_name]);
    setMessage(`已导入目录：${payload.folder_name || baseName(path)}`);
  };

  const switchSourceRoot = async () => {
    const path = await pickDirectory(data.source_root, "选择素材池目录");
    if (!path) return;
    await updateConfig({ source_root: path });
    await loadDashboard();
    setMessage(`Source folder switched: ${path}`);
  };

  const chooseOutputRoot = async () => {
    const path = await pickDirectory(data.default_output_root, "选择导出目录");
    if (!path) return;
    await updateConfig({ default_output_root: path });
    await loadDashboard();
    setMessage(`默认导出目录已更新：${path}`);
  };

  const resetOutputRoot = async () => {
    await updateConfig({ default_output_root: "" });
    await loadDashboard();
    setMessage("已恢复系统默认输出目录");
  };

  const createJob = async (source) => {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_name: source.name,
        source_path: source.path,
        name: baseName(source.name),
        output_dir: data.default_output_root,
        output_formats: selectedFormats,
        keep_original_pages: keepOriginalPages,
        keep_enhanced_pages: keepEnhancedPages,
        pdf_quality_mode: selectedPdfQualityMode,
        pdf_image_format: selectedImageFormat,
        enhancer: selectedEnhancer,
        enhance_scale: 1.5,
        waifu2x_noise: selectedWaifuNoise,
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "创建任务失败");
    return payload.job;
  };

  const startJobStep = async (jobId, step) => {
    const response = await fetch(`/api/jobs/${jobId}/run-step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "执行失败");
    return payload.job;
  };

  const startJobFull = async (jobId) => {
    const response = await fetch(`/api/jobs/${jobId}/run-full`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "执行失败");
    return payload.job;
  };

  const showTasksView = async (jobId = "", { refreshNow = true } = {}) => {
    if (jobId) setSelectedJobId(jobId);
    setIsTaskDetailOpen(false);
    setActivePage("tasks");
    if (refreshNow) {
      await loadDashboard();
    }
    window.setTimeout(() => {
      loadDashboard().catch(() => {});
    }, 600);
  };

  const mergeSelectedSources = async () => {
    if (selectedSourceItems.length < 2) {
      setMessage("至少选择两项素材后才能合并优化导出");
      return;
    }
    const response = await fetch("/api/merge-sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_names: selectedSourceItems.map((item) => item.name),
        output_dir: data.default_output_root,
        output_formats: selectedFormats,
        enhancer: selectedEnhancer,
        enhance_scale: 1.5,
        strategy: "quality_auto",
        waifu2x_noise: selectedWaifuNoise,
        waifu2x_tta: false,
        waifu2x_model: "models-cunet",
        pdf_quality_mode: selectedPdfQualityMode,
        pdf_image_format: selectedImageFormat,
        keep_original_pages: keepOriginalPages,
        keep_enhanced_pages: keepEnhancedPages,
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "合并优化导出失败");
    if (payload.job?.id) {
      upsertLocalJob(payload.job);
      setSelectedJobId(payload.job.id);
      setIsTaskDetailOpen(false);
    }
    await showTasksView(payload.job?.id || "", { refreshNow: false });
    setMessage(`已开始生成优化合集任务`);
  };

  const runCurrentModule = async ({ stayOnPage = false, sourceOverride = null } = {}) => {
    try {
      if (activePage === "export" && selectedSourceItems.length > 1) {
        throw new Error("多选导出请在执行设置中开启“多选时合并输出为单文件”，然后点击一键全部运行");
      }

      const source = sourceOverride || selectedSourceItems[0] || previewSource;
      if (!source) {
        setMessage("璇峰厛閫夋嫨绱犳潗锛屾垨鑰呭厛瀵煎叆涓€涓洰褰曘€?");
        return;
      }
      const step = activePage === "split" ? "split" : activePage === "enhance" ? "enhance_module" : "export_module";
      const job = await createJob(source);
      upsertLocalJob(job);
      const runningJob = await startJobStep(job.id, step);
      upsertLocalJob(runningJob || job);
      setSelectedJobId(job.id);
      if (!stayOnPage) {
        await showTasksView(job.id, { refreshNow: false });
      } else {
        window.setTimeout(() => {
          loadDashboard().catch(() => {});
          loadEnhancePreview(source.name).catch(() => {});
        }, 1200);
      }
      setMessage(`${formatStage(step)} ????${source.name}`);
    } catch (error) {
      setMessage(error.message || "????");
    }
  };

  const runFullPipeline = async () => {
    try {
      const sourceList = selectedSourceItems.length ? selectedSourceItems : previewSource ? [previewSource] : [];
      if (!sourceList.length) {
        setMessage("请先在右侧素材池中选择素材。");
        return;
      }
      if (mergeOutputEnabled && sourceList.length > 1) {
        await mergeSelectedSources();
        return;
      }
      const createdJobs = [];
      for (const source of sourceList) {
        const job = await createJob(source);
        upsertLocalJob(job);
        const runningJob = await startJobFull(job.id);
        upsertLocalJob(runningJob || job);
        createdJobs.push(runningJob || job);
      }
      await showTasksView(createdJobs[0]?.id || "", { refreshNow: false });
      setMessage(`已启动 ${createdJobs.length} 项素材的一键处理。`);
    } catch (error) {
      setMessage(error.message || "执行失败");
    }
  };

  const toggleSource = (name) => {
    setSelectedSources((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));
  };

  const clearSelectedSources = () => setSelectedSources([]);
  const selectAllSources = () => setSelectedSources(sortedSourceBooks.map((item) => item.name));

  const toggleFormat = (format) => {
    setSelectedFormats((current) => {
      if (current.includes(format)) return current.length === 1 ? current : current.filter((item) => item !== format);
      return [...current, format];
    });
  };

  const currentSelectionTitle = selectedSourceItems.length > 1 ? `已选 ${selectedSourceItems.length} 项素材` : selectedSourceItems[0]?.name || "尚未选择素材";
  const currentSelectionMeta = selectedSourceItems.length
    ? `${selectedSourceItems.length === 1 ? formatSourceType(selectedSourceItems[0].format) : "多素材模式"} · ${formatSize(estimatedSourceSize)}`
    : "尚未选择素材";

  const onDropFile = (event) => {
    event.preventDefault();
    setIsDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) importFile(file).catch((error) => setMessage(error.message || "导入文件失败"));
  };

  const deleteJob = async (jobId) => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(payload.error || "删除任务失败");
      if (selectedJobId === jobId) {
        setSelectedJobId("");
        setIsTaskDetailOpen(false);
      }
      await loadDashboard();
      setMessage("任务已删除");
    } catch (error) {
      setMessage(error.message || "删除任务失败");
    }
  };

  const sourcePool = (
      <SourcePool
        sources={sortedSourceBooks}
      selectedSources={selectedSources}
      onToggle={toggleSource}
      onSelectAll={selectAllSources}
      onClearSelection={clearSelectedSources}
      onSwitchDir={() => switchSourceRoot().catch((error) => setMessage(error.message || "切换素材目录失败"))}
      onImportDir={() => importFolder().catch((error) => setMessage(error.message || "导入目录失败"))}
      onOpenRoot={() => openPath(data.source_root).catch((error) => setMessage(error.message || "打开素材池失败"))}
    />
  );

  let primaryAction = null;
  if (activePage === "import") primaryAction = { label: "一键全部完成", kind: "accent-wide", onClick: runFullPipeline };
  if (activePage === "split") primaryAction = { label: "执行拆图", onClick: runCurrentModule };
  if (activePage === "enhance") primaryAction = { label: "执行提升", onClick: runCurrentModule };
  if (activePage === "settings") primaryAction = { label: "一键全部运行", kind: "accent-wide", onClick: runFullPipeline };

  let workspace = (
    <ImportWorkspace
      content={currentContent}
      isDragActive={isDragActive}
      onDragState={setIsDragActive}
      onDropFile={onDropFile}
      onImportFile={() => fileInputRef.current?.click()}
      onImportDir={() => importFolder().catch((error) => setMessage(error.message || "导入目录失败"))}
      onSwitchDir={() => switchSourceRoot().catch((error) => setMessage(error.message || "切换素材目录失败"))}
      sourcePool={sourcePool}
    />
  );

  if (activePage === "settings") {
    workspace = (
        <SettingsWorkspace
          keepOriginalPages={keepOriginalPages}
          keepEnhancedPages={keepEnhancedPages}
          onToggleOriginal={setKeepOriginalPages}
          onToggleEnhanced={setKeepEnhancedPages}
          selectedImageFormat={selectedImageFormat}
          onSelectImageFormat={setSelectedImageFormat}
          selectedPdfQualityMode={selectedPdfQualityMode}
          onSelectPdfQualityMode={setSelectedPdfQualityMode}
          enhancerModels={enhancerModels}
          selectedEnhancer={selectedEnhancer}
          onSelectEnhancer={setSelectedEnhancer}
          selectedWaifuNoise={selectedWaifuNoise}
          onSelectWaifuNoise={setSelectedWaifuNoise}
          mergeOutputEnabled={mergeOutputEnabled}
          onToggleMergeOutput={setMergeOutputEnabled}
        outputPath={data.default_output_root}
        onPickOutputPath={() => chooseOutputRoot().catch((error) => setMessage(error.message || "设置导出目录失败"))}
        onOpenOutputPath={() => openPath(data.default_output_root).catch((error) => setMessage(error.message || "打开导出目录失败"))}
        onResetOutputPath={() => resetOutputRoot().catch((error) => setMessage(error.message || "恢复默认导出目录失败"))}
        selectedFormats={selectedFormats}
        outputFormats={exportFormatOptions}
        onToggleFormat={toggleFormat}
        formatCards={exportCards}
        estimatedSourceSize={estimatedSourceSize}
        onRunFull={runFullPipeline}
        sourcePool={sourcePool}
      />
    );
  } else if (activePage === "export") {
    workspace = (
      <ExportWorkspace
        content={currentContent}
        selectedSourceLabel={baseName(previewSource?.name || "未选择素材")}
        outputPath={data.default_output_root}
        outputDevice={outputDevice}
        onOutputDeviceChange={setOutputDevice}
        mergeOutputEnabled={mergeOutputEnabled}
        onToggleMergeOutput={setMergeOutputEnabled}
        onPickOutputPath={() => chooseOutputRoot().catch((error) => setMessage(error.message || "设置导出目录失败"))}
        onOpenOutputPath={() => openPath(data.default_output_root).catch((error) => setMessage(error.message || "打开导出目录失败"))}
        formatCards={exportCards}
        onToggleFormat={toggleFormat}
        onRunExport={runCurrentModule}
        onRunFull={runFullPipeline}
        sourcePool={sourcePool}
      />
    );
  } else if (activePage === "tasks") {
    workspace = (
        <TaskWorkspace
          jobs={data.jobs}
          currentJob={currentJob}
          detailMode={isTaskDetailOpen}
          taskPage={taskPage}
          totalTaskPages={totalTaskPages}
          onTaskPageChange={setTaskPage}
          onSelectJob={(jobId) => {
            setSelectedJobId(jobId);
            setIsTaskDetailOpen(true);
        }}
        onDeleteJob={(jobId) => deleteJob(jobId)}
        onBack={() => setIsTaskDetailOpen(false)}
        onOpenWorkspace={() => openPath(currentJob?.workspace).catch((error) => setMessage(error.message || "打开工作目录失败"))}
        onOpenOutput={() => openPath(currentJob?.output_dir).catch((error) => setMessage(error.message || "打开输出目录失败"))}
      />
    );
  } else if (activePage === "enhance") {
    workspace = (
      <EnhanceWorkspace
        content={currentContent}
        sourceRoot={data.source_root}
        outputPath={data.default_output_root}
        selectedSourceItems={selectedSourceItems}
        enhancerModels={enhancerModels}
        selectedEnhancer={selectedEnhancer}
        onSelectEnhancer={setSelectedEnhancer}
        selectedImageFormat={selectedImageFormat}
        selectedPdfQualityMode={selectedPdfQualityMode}
        selectedWaifuNoise={selectedWaifuNoise}
        onSelectWaifuNoise={setSelectedWaifuNoise}
        onSwitchDir={() => switchSourceRoot().catch((error) => setMessage(error.message || "鍒囨崲绱犳潗鐩綍澶辫触"))}
        onPickOutputPath={() => chooseOutputRoot().catch((error) => setMessage(error.message || "璁剧疆瀵煎嚭鐩綍澶辫触"))}
        onRun={runCurrentModule}
        previewPair={enhancePreview}
        previewLoading={previewLoading}
        compareValue={compareValue}
        onCompareChange={setCompareValue}
        sourcePool={sourcePool}
      />
    );
  } else if (activePage !== "import") {
    workspace = (
      <ActionWorkspace content={currentContent} actionLabel={activePage === "split" ? "执行拆图" : "执行提升"} onRun={runCurrentModule} sourcePool={sourcePool} />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">漫</div>
          <div>
            <strong>{data.product_name}</strong>
            <span>本地工作台</span>
          </div>
        </div>

        <button type="button" className={`entry-card ${activePage === "import" ? "is-active" : ""}`} onClick={() => setActivePage("import")}>
          <strong>导入</strong>
          <span>批量选择漫画</span>
        </button>

        <SidebarModules
          activePage={activePage}
          isCollapsed={isFunctionGroupCollapsed}
          onToggleCollapse={() => setIsFunctionGroupCollapsed((current) => !current)}
          onSelect={setActivePage}
        />

        <button type="button" className={`side-link-card ${activePage === "settings" ? "is-active" : ""}`} onClick={() => setActivePage("settings")}>
          <strong>执行设置</strong>
          <span>保留图片、模型与导出策略</span>
        </button>

        <button
          type="button"
          className={`side-link-card ${activePage === "tasks" ? "is-active" : ""}`}
          onClick={() => {
            setIsTaskDetailOpen(false);
            setActivePage("tasks");
          }}
        >
          <strong>任务结果</strong>
          <span>查看进度条、日志、错误与输出</span>
        </button>

        <section className="sidebar-plain">
          <p className="sidebar-heading accent">当前选择</p>
          <div className={`mini-card ${selectedSourceItems.length ? "" : "empty"}`}>
            {selectedSourceItems.length ? (
              <>
                <strong>{currentSelectionTitle}</strong>
                <span>{currentSelectionMeta}</span>
              </>
            ) : (
              "尚未选择素材"
            )}
          </div>
        </section>

        <section className="sidebar-plain">
          <p className="sidebar-heading accent">批量状态</p>
          <div className="mini-card">
            <strong>{selectedFormats[0]?.toUpperCase() || "CBZ"}</strong>
            <span>本次将处理 {selectedSourceItems.length || (previewSource ? 1 : 0)} 本</span>
          </div>
        </section>
      </aside>

      <main className="workspace">
        <HeroPanel title={currentContent.heroTitle} text={currentContent.heroText} onRefresh={() => loadDashboard().catch((error) => setMessage(error.message || "刷新失败"))} primaryAction={primaryAction} />
        {message ? (
          <section className="message-bar">
            <strong>状态</strong>
            <span>{message}</span>
          </section>
        ) : null}
        <input
          ref={fileInputRef}
          type="file"
          hidden
          accept={acceptInput}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) importFile(file).catch((error) => setMessage(error.message || "导入文件失败"));
          }}
        />
        {workspace}
      </main>
    </div>
  );
}
