const BROADCAST_NODE_NUM = 4294967295;

const collectorCard = document.getElementById("collector-card");
const collectorDetail = document.getElementById("collector-detail");
const perspectiveLabel = document.getElementById("perspective-label");
const statsRow = document.getElementById("stats-row");
const nodesPanelCount = document.getElementById("nodes-panel-count");
const mapRoot = document.getElementById("leaflet-map");
const mapEmpty = document.getElementById("map-empty");
const mapNote = document.getElementById("map-note");
const nodeDetail = document.getElementById("node-detail");
const nodeList = document.getElementById("node-list");
const intelGrid = document.getElementById("intel-grid");
const intelStory = document.getElementById("intel-story");
const chatPanelSubtitle = document.getElementById("chat-panel-subtitle");
const chatFeed = document.getElementById("chat-feed");
const packetsBody = document.getElementById("packets-body");
const refreshDashboard = document.getElementById("refresh-dashboard");
const resetMap = document.getElementById("reset-map");
const packetFilters = document.getElementById("packet-filters");
const packetLimitSelect = document.getElementById("packet-limit-select");
const exportPacketsButton = document.getElementById("export-packets");
const nodeFilters = document.getElementById("node-filters");
const nodeSearch = document.getElementById("node-search");
const routeToggle = document.getElementById("route-toggle");
const mapPanel = document.getElementById("mesh-map");
const nodesPanel = document.getElementById("mesh-nodes");
const intelPanel = document.getElementById("mesh-intel");
const chatPanel = document.getElementById("mesh-chat");
const optionsPanel = document.getElementById("mesh-options");
const trafficPanel = document.getElementById("mesh-traffic");

const mapViewport = document.querySelector(".map-viewport");
const nodeRail = document.getElementById("node-rail");
const inspectorPanel = document.querySelector(".inspector-shell");
const closeInspectorBtn = document.getElementById("close-inspector");
const railToggleNodes = document.getElementById("rail-toggle-nodes");
const railToggleChat = document.getElementById("rail-toggle-chat");
const railToggleSignals = document.getElementById("rail-toggle-signals");
const railToggleTraffic = document.getElementById("rail-toggle-traffic");
const railToggleOptions = document.getElementById("rail-toggle-options");
const rosterToolbar = document.getElementById("roster-toolbar");
const appVersionLabel = document.getElementById("app-version");
const uiThemeSelect = document.getElementById("ui-theme-select");
const uiLanguageSelect = document.getElementById("ui-language-select");
const statusBarDotForward = document.getElementById("status-bar-dot-forward");
const statusBarLabelForward = document.getElementById("status-bar-label-forward");
const statusBarDotReturn = document.getElementById("status-bar-dot-return");
const statusBarLabelReturn = document.getElementById("status-bar-label-return");
const statusBarDotTertiary = document.getElementById("status-bar-dot-tertiary");
const statusBarLabelTertiary = document.getElementById("status-bar-label-tertiary");

const i18n = window.MeshseerI18n;
const t = (key, params) => i18n.t(key, params);
const currentIntlLocale = () => i18n.intlLocale();

const TIME_FORMAT_OPTIONS = Object.freeze({
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const NODE_DECAY_WINDOW_MINUTES = 24 * 60;
const DECAY_REPAINT_INTERVAL_MS = 60_000;
const DEFAULT_RECENT_ACTIVITY_WINDOW_MINUTES = 60;
const DEFAULT_NODE_ACTIVE_WINDOW_MINUTES = 180;
const DAILY_HEARD_NODES_WINDOW_DAYS = 30;
const NETWORK_ROUTE_WINDOW_MINUTES = 7 * 24 * 60;
const SELECTED_ROUTE_WINDOW_MINUTES = 7 * 24 * 60;
const PACKETS_LIMIT = 40;
const PACKET_LIMIT_OPTIONS = Object.freeze([40, 100, 200]);
const PACKETS_API_MAX_LIMIT = 500;
const PACKETS_FETCH_STEP = 50;
const CHAT_MESSAGES_LIMIT = 40;
const MAX_ACTIVITY_PACKETS = 500;
const KPI_STALE_WINDOW_MINUTES = 10;
const NODE_MAX_OPACITY = 0.94;
const NODE_MIN_OPACITY = 0.14;
const ROUTE_MAX_OPACITY = 0.55;
const ROUTE_MIN_OPACITY = 0.08;
const CHAT_STICKY_THRESHOLD_PX = 16;
const SUMMARY_REFRESH_DEBOUNCE_MS = 750;
const ROUTES_REFRESH_DEBOUNCE_MS = 1000;
const NODE_DETAIL_REFRESH_DEBOUNCE_MS = 500;
const SOCKET_POLICY_CLOSE_CODE = 1008;
const SOCKET_TRY_AGAIN_LATER_CLOSE_CODE = 1013;
const SOCKET_FAST_RECONNECT_DELAY_MS = 1500;
const SOCKET_BACKOFF_BASE_DELAY_MS = 1500;
const SOCKET_BACKOFF_MAX_DELAY_MS = 30_000;
const UI_THEME_STORAGE_KEY = "meshseer.ui.theme";
const LEGACY_UI_STYLE_STORAGE_KEY = "meshseer.ui.style";
const PACKET_LIMIT_STORAGE_KEY = "meshseer.packet.limit";
const DEFAULT_UI_THEME = "amber-monochrome";
const CARTO_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO';
const CARTO_TILE_OPTIONS = Object.freeze({
  subdomains: "abcd",
  maxZoom: 20,
});
const CSV_FORMULA_TEXT_PATTERN = /^[=+\-@]/;

function cartoLayer(path, options = {}) {
  return {
    url: `https://{s}.basemaps.cartocdn.com/${path}/{z}/{x}/{y}{r}.png`,
    options: {
      ...CARTO_TILE_OPTIONS,
      attribution: CARTO_ATTRIBUTION,
      ...options,
    },
  };
}

function defineTheme({ id, label, basemapLayers, overlay }) {
  return Object.freeze({
    id,
    label,
    basemapLayers: Object.freeze(basemapLayers),
    overlay: Object.freeze(overlay),
  });
}

const THEME_REGISTRY = Object.freeze({
  "amber-monochrome": defineTheme({
    id: "amber-monochrome",
    label: "Amber Monochrome",
    basemapLayers: [
      cartoLayer("dark_nolabels"),
      cartoLayer("dark_only_labels", {
        opacity: 0.4,
        pane: "overlayPane",
      }),
    ],
    overlay: {
      markerShape: "radar",
      markerLabelColor: "#e8dcc8",
      routeColor: "#e8a94d",
      routeReturnColor: "#d59b47",
      routeSelectedColor: "#fff3db",
      routeArrowColor: "#ffffff",
      routeArrowStrokeColor: "none",
      preserveRouteColorOnSelect: false,
      routeLegend: {
        forward: { labelKey: "routes.forward", color: "#e8a94d" },
        return: { labelKey: "routes.return", color: "#d59b47" },
        tertiary: { labelKey: "routes.older", color: "rgba(255, 255, 255, 0.2)" },
      },
      markerPalette: {
        direct: {
          fillColor: "#e8a94d",
          glyphColor: "#2f1a03",
          borderColor: "#f5b862",
          haloColor: "rgba(232, 169, 77, 0.35)",
        },
        relayed: {
          fillColor: "#d39a4f",
          glyphColor: "#2f1a03",
          borderColor: "#c49455",
          haloColor: "rgba(232, 169, 77, 0.22)",
        },
        mqtt: {
          fillColor: "#7d8ea1",
          glyphColor: "#11161b",
          borderColor: "#9eb0c2",
          haloColor: "rgba(158, 176, 194, 0.22)",
        },
        selected: {
          borderColor: "#fff3db",
          haloColor: "rgba(255, 243, 219, 0.35)",
        },
      },
    },
  }),
  classic: defineTheme({
    id: "classic",
    label: "Classic (light)",
    basemapLayers: [
      cartoLayer("rastertiles/voyager"),
    ],
    overlay: {
      markerShape: "pin",
      markerLabelColor: "#314551",
      routeColor: "#4f86c6",
      routeReturnColor: "#68a95f",
      routeSelectedColor: "#2f7c91",
      preserveRouteColorOnSelect: true,
      routeLegend: {
        forward: { labelKey: "routes.forward", color: "#4f86c6" },
        return: { labelKey: "routes.return", color: "#68a95f" },
        tertiary: { label: "", color: "transparent" },
      },
      markerPalette: {
        direct: {
          fillColor: "#4f86c6",
          glyphColor: "#f8fbfd",
          borderColor: "#2f5d8a",
          haloColor: "rgba(79, 134, 198, 0.28)",
        },
        relayed: {
          fillColor: "#68a95f",
          glyphColor: "#f8fbfd",
          borderColor: "#4b7f45",
          haloColor: "rgba(104, 169, 95, 0.24)",
        },
        mqtt: {
          fillColor: "#b978c6",
          glyphColor: "#fdf9ff",
          borderColor: "#875292",
          haloColor: "rgba(185, 120, 198, 0.24)",
        },
        selected: {
          borderColor: "#245d6d",
          haloColor: "rgba(47, 124, 145, 0.26)",
        },
      },
    },
  }),
  "classic-dark": defineTheme({
    id: "classic-dark",
    label: "Classic (dark)",
    basemapLayers: [
      cartoLayer("dark_nolabels"),
      cartoLayer("dark_only_labels", {
        opacity: 0.45,
        pane: "overlayPane",
      }),
    ],
    overlay: {
      markerShape: "pin",
      markerLabelColor: "#d8e5ee",
      routeColor: "#6ea8de",
      routeReturnColor: "#78c06d",
      routeSelectedColor: "#d9edf4",
      preserveRouteColorOnSelect: true,
      routeLegend: {
        forward: { labelKey: "routes.forward", color: "#6ea8de" },
        return: { labelKey: "routes.return", color: "#78c06d" },
        tertiary: { label: "", color: "transparent" },
      },
      markerPalette: {
        direct: {
          fillColor: "#6ea8de",
          glyphColor: "#0f1820",
          borderColor: "#8ebde7",
          haloColor: "rgba(110, 168, 222, 0.3)",
        },
        relayed: {
          fillColor: "#78c06d",
          glyphColor: "#0f1820",
          borderColor: "#97d28e",
          haloColor: "rgba(120, 192, 109, 0.28)",
        },
        mqtt: {
          fillColor: "#c694d3",
          glyphColor: "#1f1124",
          borderColor: "#d7afdf",
          haloColor: "rgba(198, 148, 211, 0.26)",
        },
        selected: {
          borderColor: "#d9edf4",
          haloColor: "rgba(217, 237, 244, 0.24)",
        },
      },
    },
  }),
});

const pulseTimers = new WeakMap();
const inflightNodeDetails = new Set();
const inflightLoads = new Map();
const scheduledRefreshes = new Map();
let decayRefreshTimerId = null;
let chatStickToBottom = true;
let chatPendingScrollBehavior = null;
let chatLastMessageKey = null;
let socketReconnectTimerId = null;
let socketReconnectAttempts = 0;

const state = {
  nodes: [],
  packets: [],
  recentActivityPackets: [],
  chat: [],
  perspective: null,
  collectorStatus: null,
  selectedNodeNum: null,
  remoteNodeNums: new Set(),
  packetFilter: "all",
  nodeFilters: new Set(),
  nodeQuery: "",
  showRoutes: true,
  meshSummary: null,
  meshRoutes: { routes: [], stats: { total: 0, forward: 0, return: 0 } },
  drawnRouteCount: null,
  nodeDetails: new Map(),
  nodeDetailLoadingNodeNum: null,
  nodeDetailErrorNodeNum: null,
  socketState: "booting",
  lastUpdatedAt: null,
  lastPacketReceivedAt: null,
  nodesDrawerOpen: true,
  activeDrawerView: "nodes",
  trafficDrawerOpen: false,
  meshSummaryPrevious: null,
  uiDefaultTheme: DEFAULT_UI_THEME,
  currentTheme: DEFAULT_UI_THEME,
  packetLimit: PACKETS_LIMIT,
};

const mapState = {
  map: null,
  routeLayer: null,
  routeArrowLayer: null,
  markerLayer: null,
  markersByNodeNum: new Map(),
  routeLinesByKey: new Map(),
  initialViewApplied: false,
  zoomListenerBound: false,
  basemapLayers: [],
};

const reducedMotionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeThemeId(value) {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(THEME_REGISTRY, normalized) ? normalized : null;
}

function normalizePacketLimit(value) {
  const numericValue = Number(value);
  return PACKET_LIMIT_OPTIONS.includes(numericValue) ? numericValue : null;
}

function currentThemeDefinition() {
  return THEME_REGISTRY[state.currentTheme] || THEME_REGISTRY[DEFAULT_UI_THEME];
}

function currentThemeOverlay() {
  return currentThemeDefinition().overlay || THEME_REGISTRY[DEFAULT_UI_THEME].overlay;
}

function renderStatusBarLegend() {
  const overlay = currentThemeOverlay();
  const legend = overlay.routeLegend || {
    forward: { labelKey: "routes.forward", color: overlay.routeColor },
    return: { labelKey: "routes.return", color: overlay.routeReturnColor },
    tertiary: { labelKey: "common.selected", color: overlay.routeSelectedColor },
  };
  const legendLabel = (item) => (item.labelKey ? t(item.labelKey) : (item.label || ""));
  if (statusBarDotForward) {
    statusBarDotForward.style.background = legend.forward.color;
  }
  if (statusBarLabelForward) {
    statusBarLabelForward.textContent = legendLabel(legend.forward);
  }
  if (statusBarDotReturn) {
    statusBarDotReturn.style.background = legend.return.color;
  }
  if (statusBarLabelReturn) {
    statusBarLabelReturn.textContent = legendLabel(legend.return);
  }
  const tertiaryLabel = legendLabel(legend.tertiary);
  if (statusBarDotTertiary) {
    statusBarDotTertiary.style.background = legend.tertiary.color;
    statusBarDotTertiary.hidden = !tertiaryLabel;
  }
  if (statusBarLabelTertiary) {
    statusBarLabelTertiary.textContent = tertiaryLabel;
    statusBarLabelTertiary.hidden = !tertiaryLabel;
  }
}

function readStoredThemeId() {
  try {
    const savedTheme = window.localStorage.getItem(UI_THEME_STORAGE_KEY);
    const normalizedTheme = normalizeThemeId(savedTheme);
    if (savedTheme != null) {
      if (normalizedTheme == null) {
        window.localStorage.removeItem(UI_THEME_STORAGE_KEY);
      }
      return normalizedTheme;
    }

    const legacyStyle = window.localStorage.getItem(LEGACY_UI_STYLE_STORAGE_KEY);
    const normalizedLegacyTheme = normalizeThemeId(legacyStyle);
    if (legacyStyle != null) {
      window.localStorage.removeItem(LEGACY_UI_STYLE_STORAGE_KEY);
      if (normalizedLegacyTheme != null) {
        window.localStorage.setItem(UI_THEME_STORAGE_KEY, normalizedLegacyTheme);
      }
      return normalizedLegacyTheme;
    }

    return null;
  } catch (_error) {
    return null;
  }
}

function readStoredPacketLimit() {
  try {
    const savedLimit = window.localStorage.getItem(PACKET_LIMIT_STORAGE_KEY);
    const normalizedLimit = normalizePacketLimit(savedLimit);
    if (savedLimit != null && normalizedLimit == null) {
      window.localStorage.removeItem(PACKET_LIMIT_STORAGE_KEY);
    }
    return normalizedLimit;
  } catch (_error) {
    return null;
  }
}

function writeStoredThemeId(themeId) {
  try {
    window.localStorage.setItem(UI_THEME_STORAGE_KEY, themeId);
    window.localStorage.removeItem(LEGACY_UI_STYLE_STORAGE_KEY);
  } catch (_error) {
    return false;
  }
  return true;
}

function writeStoredPacketLimit(limit) {
  try {
    window.localStorage.setItem(PACKET_LIMIT_STORAGE_KEY, String(limit));
  } catch (_error) {
    return false;
  }
  return true;
}

function removeStoredThemeId() {
  try {
    window.localStorage.removeItem(UI_THEME_STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_UI_STYLE_STORAGE_KEY);
  } catch (_error) {
    return false;
  }
  return true;
}

function syncThemeControls() {
  if (uiThemeSelect) {
    uiThemeSelect.value = state.currentTheme;
  }
}

function syncLanguageControls() {
  if (uiLanguageSelect) {
    uiLanguageSelect.value = i18n.locale();
  }
}

function syncPacketLimitControl() {
  if (packetLimitSelect) {
    packetLimitSelect.value = String(state.packetLimit);
  }
}

function applyBasemapTheme() {
  if (!mapState.map) {
    return;
  }
  mapState.basemapLayers.forEach((layer) => {
    mapState.map.removeLayer(layer);
  });
  mapState.basemapLayers = currentThemeDefinition().basemapLayers.map((definition) => {
    const layer = L.tileLayer(definition.url, definition.options);
    layer.addTo(mapState.map);
    return layer;
  });
}

function renderThemeDependentMapLayers() {
  if (!mapState.map || !state.nodes.length) {
    return;
  }
  renderMap(state.nodes);
}

function syncThemeCssProperties(theme = currentThemeDefinition()) {
  const rootStyle = document.documentElement.style;
  const overlay = theme.overlay || {};
  const palette = overlay.markerPalette || {};
  rootStyle.setProperty("--map-node-direct", palette.direct?.fillColor || "#e8a94d");
  rootStyle.setProperty("--map-node-relayed", palette.relayed?.fillColor || "#d39a4f");
  rootStyle.setProperty("--map-node-mqtt", palette.mqtt?.fillColor || "#7d8ea1");
  rootStyle.setProperty("--map-route-forward", overlay.routeColor || "#e8a94d");
  rootStyle.setProperty("--map-route-return", overlay.routeReturnColor || "#d59b47");
}

function applyThemeSelection(themeId, { persist = false } = {}) {
  const normalized = normalizeThemeId(themeId) || DEFAULT_UI_THEME;
  const theme = THEME_REGISTRY[normalized];
  const themeChanged = state.currentTheme !== normalized
    || document.documentElement.dataset.theme !== normalized;
  state.currentTheme = normalized;
  document.documentElement.dataset.theme = normalized;
  syncThemeCssProperties(theme);
  syncThemeControls();
  renderStatusBarLegend();
  if (themeChanged) {
    applyBasemapTheme();
    renderThemeDependentMapLayers();
  }
  if (persist) {
    writeStoredThemeId(normalized);
  }
  return normalized;
}

function resolveStartupTheme(serverDefaultStyle) {
  return readStoredThemeId() || normalizeThemeId(serverDefaultStyle) || DEFAULT_UI_THEME;
}

function formatTime(value) {
  if (!value) {
    return t("common.na");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat(currentIntlLocale(), TIME_FORMAT_OPTIONS).format(date);
}

function formatRelativeTime(value, nowMs = Date.now()) {
  const ageMinutes = ageMinutesSince(value, nowMs);
  if (ageMinutes == null) {
    return t("common.na");
  }
  if (ageMinutes < 1) {
    return t("relative.justNow");
  }
  if (ageMinutes < 60) {
    return t("relative.minutesAgo", { count: Math.floor(ageMinutes) });
  }
  if (ageMinutes < 24 * 60) {
    return t("relative.hoursAgo", { count: Math.floor(ageMinutes / 60) });
  }
  if (ageMinutes < 7 * 24 * 60) {
    return t("relative.daysAgo", { count: Math.floor(ageMinutes / (24 * 60)) });
  }
  return formatTime(value);
}

function formatLastUpdated(value) {
  if (!value) {
    return t("common.waiting");
  }
  return formatTime(value);
}

function formatNumber(value, digits = 1, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) {
    return t("common.na");
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatWholeNumber(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return t("common.na");
  }
  return new Intl.NumberFormat(currentIntlLocale()).format(Math.round(Number(value)));
}

function csvEscape(value) {
  const text = csvSafeCellText(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function csvSafeCellText(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  const text = String(value ?? "");
  const trimmedLeading = text.trimStart();
  if (/^[\t\r\n]/.test(text) || (trimmedLeading && CSV_FORMULA_TEXT_PATTERN.test(trimmedLeading[0]))) {
    return `'${text}`;
  }
  return text;
}

function fileTimestampPart(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("")
    + "-"
    + [
      pad(date.getHours()),
      pad(date.getMinutes()),
      pad(date.getSeconds()),
    ].join("");
}

function formatCompactChange(value, digits = 0, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) {
    return t("common.na");
  }
  return `${Math.abs(Number(value)).toFixed(digits)}${suffix}`;
}

function titleCase(value) {
  return String(value ?? "")
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function interpolate(start, end, ratio) {
  return start + ((end - start) * ratio);
}

function parseUtcDateMs(value) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.getTime();
}

function utcDayKey(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString().slice(0, 10);
}

function shiftUtcDays(date, days) {
  return new Date(Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate() + days,
  ));
}

function ageMinutesSince(value, nowMs = Date.now()) {
  const parsedMs = parseUtcDateMs(value);
  if (parsedMs == null) {
    return null;
  }
  return Math.max(0, (nowMs - parsedMs) / 60000);
}

function recentPacketWindowMinutes() {
  return Number(state.meshSummary?.windowed_activity?.window_minutes) || DEFAULT_RECENT_ACTIVITY_WINDOW_MINUTES;
}

function meshRouteWindowMinutes() {
  return Math.max(NETWORK_ROUTE_WINDOW_MINUTES, SELECTED_ROUTE_WINDOW_MINUTES);
}

function nodeActiveWindowMinutes() {
  return Number(state.meshSummary?.nodes?.active_window_minutes) || DEFAULT_NODE_ACTIVE_WINDOW_MINUTES;
}

function isoMinutesAgo(minutes, nowMs = Date.now()) {
  return toUtcIso(new Date(nowMs - (minutes * 60_000)));
}

function setLastPacketReceivedAt(timestamp) {
  if (!timestamp) {
    return;
  }
  const parsed = parseUtcDateMs(timestamp);
  if (parsed == null) {
    return;
  }
  if (state.lastPacketReceivedAt == null || parsed > parseUtcDateMs(state.lastPacketReceivedAt)) {
    state.lastPacketReceivedAt = timestamp;
  }
}

function decayFraction(ageMinutes, windowMinutes) {
  if (ageMinutes == null) {
    return 1;
  }
  return clamp(ageMinutes / windowMinutes, 0, 1);
}

function nodeDecayFraction(node, nowMs = Date.now()) {
  if (isLocalNode(node)) {
    return 0;
  }
  return decayFraction(ageMinutesSince(node?.last_heard_at, nowMs), NODE_DECAY_WINDOW_MINUTES);
}

function nodeIsVisible(node, nowMs = Date.now()) {
  if (!node) {
    return false;
  }
  if (isLocalNode(node)) {
    return true;
  }
  const ageMinutes = ageMinutesSince(node?.last_heard_at, nowMs);
  return ageMinutes != null && ageMinutes < NODE_DECAY_WINDOW_MINUTES;
}

function routeDecayFraction(route, nowMs = Date.now()) {
  const pathNodeNums = Array.isArray(route?.path_node_nums) ? route.path_node_nums : [];
  if (!pathNodeNums.length) {
    return 1;
  }
  return Math.max(
    ...pathNodeNums.map((nodeNum) => nodeDecayFraction(nodeByNum(nodeNum), nowMs)),
  );
}

function toUtcIso(date) {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function nodeLabel(node) {
  return node?.short_name || node?.long_name || node?.node_id || t("common.nodeWithNum", { num: node?.node_num ?? "?" });
}

function nodeSecondaryLabel(node) {
  if (!node) {
    return "";
  }
  if (node.long_name && node.long_name !== node.short_name) {
    return node.long_name;
  }
  if (node.node_id) {
    return node.node_id;
  }
  return t("common.nodeWithNum", { num: node.node_num });
}

function nodeByNum(nodeNum) {
  return state.nodes.find((item) => item.node_num === nodeNum) || null;
}

function packetKey(packet) {
  return packet?.id ?? packet?.mesh_packet_id ?? packet?.received_at ?? null;
}

function prependUniqueItem(items, item, { limit, keyFor }) {
  if (!item) {
    return Array.isArray(items) ? items : [];
  }
  const nextKey = keyFor(item);
  return [
    item,
    ...(Array.isArray(items) ? items : []).filter((candidate) => {
      if (!candidate) {
        return false;
      }
      const candidateKey = keyFor(candidate);
      if (nextKey != null && candidateKey != null) {
        return candidateKey !== nextKey;
      }
      return candidate !== item;
    }),
  ].slice(0, limit);
}

function upsertRosterNode(node) {
  if (!node || node.node_num == null) {
    return null;
  }

  const existingIndex = state.nodes.findIndex((item) => item.node_num === node.node_num);
  const nextNode = syncRosterNodeMeta({
    ...(existingIndex >= 0 ? state.nodes[existingIndex] : {}),
    ...node,
  });

  if (existingIndex < 0) {
    state.nodes = [nextNode, ...state.nodes];
    return nextNode;
  }

  state.nodes = [
    ...state.nodes.slice(0, existingIndex),
    nextNode,
    ...state.nodes.slice(existingIndex + 1),
  ];
  return nextNode;
}

function prependPacket(packet) {
  state.packets = prependUniqueItem(state.packets, packet, {
    limit: packetStorageLimit(state.packets.length + 1),
    keyFor: packetKey,
  });
  queuePacketTopUp();
}

function prependChatMessage(message) {
  state.chat = prependUniqueItem(state.chat, message, {
    limit: CHAT_MESSAGES_LIMIT,
    keyFor: chatMessageKey,
  });
}

function runSingleFlight(key, loader) {
  const existing = inflightLoads.get(key);
  if (existing) {
    return existing;
  }
  const pending = Promise.resolve()
    .then(() => loader())
    .finally(() => {
      if (inflightLoads.get(key) === pending) {
        inflightLoads.delete(key);
      }
    });
  inflightLoads.set(key, pending);
  return pending;
}

function scheduledRefreshEntry(key) {
  if (!scheduledRefreshes.has(key)) {
    scheduledRefreshes.set(key, {
      timerId: null,
      inflight: false,
      dirty: false,
      deferred: false,
      loader: null,
    });
  }
  return scheduledRefreshes.get(key);
}

async function runScheduledRefresh(key) {
  const entry = scheduledRefreshEntry(key);
  const loader = entry.loader;
  if (typeof loader !== "function") {
    return;
  }
  if (entry.timerId != null) {
    window.clearTimeout(entry.timerId);
    entry.timerId = null;
  }
  if (entry.inflight) {
    entry.dirty = true;
    return;
  }
  if (document.visibilityState !== "visible") {
    entry.deferred = true;
    return;
  }

  entry.inflight = true;
  entry.dirty = false;
  entry.deferred = false;

  try {
    await loader();
  } catch (error) {
    handleLoadError(error);
  } finally {
    entry.inflight = false;
    if (document.visibilityState !== "visible") {
      entry.deferred = entry.deferred || entry.dirty;
      entry.dirty = false;
      return;
    }
    if (entry.dirty || entry.deferred) {
      entry.dirty = false;
      entry.deferred = false;
      entry.timerId = window.setTimeout(() => {
        entry.timerId = null;
        void runScheduledRefresh(key);
      }, 0);
    }
  }
}

function scheduleRefresh(key, delayMs, loader) {
  const entry = scheduledRefreshEntry(key);
  entry.loader = loader;
  if (entry.timerId != null) {
    window.clearTimeout(entry.timerId);
    entry.timerId = null;
  }
  if (document.visibilityState !== "visible") {
    entry.deferred = true;
    return;
  }
  if (entry.inflight) {
    entry.dirty = true;
    return;
  }
  entry.deferred = false;
  entry.timerId = window.setTimeout(() => {
    entry.timerId = null;
    void runScheduledRefresh(key);
  }, delayMs);
}

function clearQueuedRefreshes() {
  scheduledRefreshes.forEach((entry) => {
    if (entry.timerId != null) {
      window.clearTimeout(entry.timerId);
      entry.timerId = null;
    }
    entry.dirty = false;
    entry.deferred = false;
  });
}

function flushDeferredRefreshes() {
  if (document.visibilityState !== "visible") {
    return;
  }
  scheduledRefreshes.forEach((entry, key) => {
    if (!entry.deferred) {
      return;
    }
    entry.deferred = false;
    scheduleRefresh(key, 0, entry.loader);
  });
}

function scheduleMeshSummaryRefresh() {
  scheduleRefresh("meshSummary", SUMMARY_REFRESH_DEBOUNCE_MS, () => loadMeshSummary());
}

function scheduleMeshRoutesRefresh() {
  scheduleRefresh("meshRoutes", ROUTES_REFRESH_DEBOUNCE_MS, () => loadMeshRoutes());
}

function scheduleSelectedNodeDetailRefresh(nodeNum = state.selectedNodeNum) {
  if (nodeNum == null) {
    return;
  }
  const key = `nodeDetail:${nodeNum}`;
  scheduleRefresh(key, NODE_DETAIL_REFRESH_DEBOUNCE_MS, async () => {
    if (state.selectedNodeNum !== nodeNum || !nodeByNum(nodeNum)) {
      return;
    }
    await loadNodeDetail(nodeNum, { force: true });
  });
}

function nodeStatus(node) {
  if (!node) {
    return "relayed";
  }
  if (isLocalNode(node)) {
    return "direct";
  }
  const explicit = String(node.status || "").toLowerCase();
  if (explicit === "local" || explicit === "mqtt" || explicit === "direct" || explicit === "relayed") {
    return explicit === "local" ? "direct" : explicit;
  }
  if (node?.via_mqtt) {
    return "mqtt";
  }
  if (node?.hops_away != null && Number(node.hops_away) <= 1) {
    return "direct";
  }
  return "relayed";
}

function nodeIsDirectRf(node) {
  return nodeStatus(node) === "direct";
}

function nodeIsMqtt(node) {
  if (typeof node?.is_mqtt === "boolean") {
    return node.is_mqtt;
  }
  return nodeStatus(node) === "mqtt";
}

function nodeIsActive(node, nowMs = Date.now()) {
  if (!node) {
    return false;
  }
  const windowMinutes = nodeActiveWindowMinutes();
  const heardAgeMinutes = ageMinutesSince(node?.last_heard_at, nowMs);
  return heardAgeMinutes != null && heardAgeMinutes <= windowMinutes;
}

function nodeIsStale(node) {
  if (!node) {
    return false;
  }
  const minutes = ageMinutesSince(node?.last_heard_at);
  return minutes != null && minutes > 1440;
}

function syncRosterNodeMeta(node) {
  if (!node) {
    return node;
  }
  node.status = nodeStatus(node);
  node.is_active = nodeIsActive(node);
  node.is_direct_rf = nodeIsDirectRf(node);
  node.is_mapped = nodeHasCoordinates(node);
  node.is_mqtt = nodeIsMqtt(node);
  node.is_stale = nodeFreshness(node) === "stale";
  node.activity_count_60m = intValue(node.activity_count_60m);
  return node;
}

function observePacketNode(packet) {
  const nodeNum = packet?.from_node_num;
  if (nodeNum == null) {
    return;
  }

  const countsForRecentActivity = packetCountsForRecentActivity(packet);
  const receivedAt = packet?.received_at || null;
  const packetHops = packetHopsTaken(packet);
  const pathTone = packetPathTone(packet);
  const existing = nodeByNum(nodeNum);
  if (!existing) {
    const nextNode = syncRosterNodeMeta({
      node_num: nodeNum,
      node_id: null,
      short_name: null,
      long_name: null,
      hardware_model: null,
      role: null,
      channel_index: null,
      last_heard_at: receivedAt,
      last_snr: null,
      latitude: null,
      longitude: null,
      altitude: null,
      battery_level: null,
      channel_utilization: null,
      air_util_tx: null,
      raw_json: "{}",
      updated_at: receivedAt,
      hops_away: packetHops,
      via_mqtt: pathTone === "mqtt" ? true : null,
      activity_count_60m: countsForRecentActivity ? 1 : 0,
    });
    state.nodes = [nextNode, ...state.nodes];
    return;
  }

  if (!existing.last_heard_at || (receivedAt && existing.last_heard_at <= receivedAt)) {
    existing.last_heard_at = receivedAt;
  }
  if (existing.via_mqtt == null && pathTone === "mqtt") {
    existing.via_mqtt = true;
  }
  if (existing.hops_away == null && packetHops != null) {
    existing.hops_away = packetHops;
  }
  if (countsForRecentActivity) {
    existing.activity_count_60m = intValue(existing.activity_count_60m) + 1;
  }
  syncRosterNodeMeta(existing);
}

function nodeHasCoordinates(node) {
  return Boolean(node) && typeof node.latitude === "number" && typeof node.longitude === "number";
}

function isLocalNode(node) {
  return node?.node_num === state.perspective?.local_node_num;
}

function isDirectNode(node) {
  if (isLocalNode(node)) {
    return true;
  }
  return nodeIsDirectRf(node);
}

function isMultiHopNode(node) {
  if (isLocalNode(node) || node?.via_mqtt || node?.hops_away == null) {
    return false;
  }
  return Number(node.hops_away) > 1;
}

function packetHopsTaken(packet) {
  if (!packet) {
    return null;
  }
  const pathTone = packetPathTone(packet);
  if (pathTone === "mqtt" || pathTone === "unknown") {
    return null;
  }
  if (pathTone === "local") {
    return 0;
  }
  if (pathTone === "direct") {
    return 0;
  }
  const match = String(packetPathLabel(packet)).match(/^(\d+)/);
  if (!match) {
    return null;
  }
  const hops = Number(match[1]);
  return Number.isFinite(hops) ? hops : null;
}

function packetPathTone(packet) {
  return packet?.path_tone || "unknown";
}

function packetPathLabel(packet) {
  const rawLabel = packet?.path_label;
  if (typeof rawLabel === "string" && rawLabel.trim()) {
    const normalized = rawLabel.trim().toLowerCase();
    const hopMatch = normalized.match(/^(\d+)\s+hops?$/);
    if (normalized === "mqtt") {
      return t("path.mqtt");
    }
    if (normalized === "unknown") {
      return t("common.unknown");
    }
    if (normalized === "local") {
      return t("common.local");
    }
    if (normalized === "direct") {
      return t("path.direct");
    }
    if (hopMatch) {
      const hopCount = Number(hopMatch[1]);
      return hopCount === 1 ? t("path.oneHop") : t("path.hops", { count: hopCount });
    }
    return rawLabel;
  }
  return t("common.unknown");
}

function nodePathTone(node) {
  const status = nodeStatus(node);
  if (status === "local") {
    return "local";
  }
  if (status === "mqtt") {
    return "mqtt";
  }
  if (node?.hops_away == null) {
    return "unknown";
  }
  return Number(node.hops_away) <= 1 ? "direct" : "relayed";
}

function detailTraceroutePath(detailPayload, node) {
  const localNodeNum = Number(state.perspective?.local_node_num);
  const nodeNum = Number(node?.node_num);
  if (!Number.isFinite(nodeNum)) {
    return [];
  }

  const candidatePaths = [
    detailPayload?.latest_complete_traceroute?.forward_path_node_nums,
    detailPayload?.last_successful_traceroute_attempt?.route?.path_node_nums,
    detailPayload?.last_traceroute_attempt?.route?.path_node_nums,
  ];

  for (const candidate of candidatePaths) {
    const pathNodeNums = (Array.isArray(candidate) ? candidate : [])
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value));
    if (pathNodeNums.length < 2) {
      continue;
    }

    const startNodeNum = pathNodeNums[0];
    const endNodeNum = pathNodeNums[pathNodeNums.length - 1];
    if (Number.isFinite(localNodeNum)) {
      if (startNodeNum === localNodeNum && endNodeNum === nodeNum) {
        return pathNodeNums;
      }
      if (startNodeNum === nodeNum && endNodeNum === localNodeNum) {
        return [...pathNodeNums].reverse();
      }
    }
    if (endNodeNum === nodeNum) {
      return pathNodeNums;
    }
    if (startNodeNum === nodeNum) {
      return [...pathNodeNums].reverse();
    }
  }

  return [];
}

function effectiveNodeHopCount(node, detailPayload = null) {
  const traceroutePath = detailTraceroutePath(detailPayload, node);
  if (traceroutePath.length >= 2) {
    return Math.max(0, traceroutePath.length - 2);
  }
  if (node?.hops_away == null) {
    return null;
  }
  const hopsAway = Number(node.hops_away);
  return Number.isFinite(hopsAway) ? hopsAway : null;
}

function nodePathLabel(node, detailPayload = null) {
  if (isLocalNode(node)) {
    return t("common.local");
  }
  const status = nodeStatus(node);
  if (status === "mqtt") {
    return t("path.mqtt");
  }
  const hopCount = effectiveNodeHopCount(node, detailPayload);
  if (hopCount == null) {
    return t("path.pathUnknown");
  }
  if (hopCount === 0) {
    return t("path.direct");
  }
  if (hopCount === 1) {
    return t("path.oneHop");
  }
  return t("path.hops", { count: hopCount });
}

function nodePathDescription(node, detailPayload = null) {
  if (isLocalNode(node)) {
    return t("path.receiverLocal");
  }
  const status = nodeStatus(node);
  if (status === "mqtt") {
    return t("path.throughMqtt");
  }
  const hopCount = effectiveNodeHopCount(node, detailPayload);
  if (hopCount == null) {
    return t("path.noEstimate");
  }
  if (hopCount === 0) {
    return t("path.directFromReceiver");
  }
  return t("path.hopsFromReceiver", { count: hopCount });
}

function nodeSignalOpacity(node, nowMs = Date.now()) {
  return interpolate(NODE_MAX_OPACITY, NODE_MIN_OPACITY, nodeDecayFraction(node, nowMs));
}

function routeSignalOpacity(route, nowMs = Date.now()) {
  return interpolate(ROUTE_MAX_OPACITY, ROUTE_MIN_OPACITY, routeDecayFraction(route, nowMs));
}

function routeIsVisible(route, nowMs = Date.now()) {
  const pathNodeNums = Array.isArray(route?.path_node_nums) ? route.path_node_nums : [];
  if (pathNodeNums.length < 2) {
    return false;
  }
  return pathNodeNums.every((nodeNum) => {
    const node = nodeByNum(nodeNum);
    return nodeHasCoordinates(node) && nodeIsVisible(node, nowMs);
  });
}

function routeIdentityKey(route) {
  return [
    route?.direction || "",
    Array.isArray(route?.path_node_nums) ? route.path_node_nums.join(">") : "",
  ].join(":");
}

function routeKey(route) {
  return route?.group_key || routeIdentityKey(route);
}

function routePairKey(route) {
  const sourceNodeNum = Number(route?.source_node_num);
  const destinationNodeNum = Number(route?.destination_node_num);
  if (!Number.isFinite(sourceNodeNum) || !Number.isFinite(destinationNodeNum)) {
    return null;
  }
  return sourceNodeNum < destinationNodeNum
    ? `${sourceNodeNum}:${destinationNodeNum}`
    : `${destinationNodeNum}:${sourceNodeNum}`;
}

function routeSeenAt(route) {
  return route?.received_at || route?.latest_received_at || "";
}

function compareRoutesByRecency(left, right) {
  const leftSeen = routeSeenAt(left);
  const rightSeen = routeSeenAt(right);
  if (leftSeen !== rightSeen) {
    return rightSeen.localeCompare(leftSeen);
  }
  const leftPacketId = intValue(left?.packet_id || left?.mesh_packet_id);
  const rightPacketId = intValue(right?.packet_id || right?.mesh_packet_id);
  if (leftPacketId !== rightPacketId) {
    return rightPacketId - leftPacketId;
  }
  return String(left?.direction || "").localeCompare(String(right?.direction || ""));
}

function routeAgeMinutes(route, nowMs = Date.now()) {
  return ageMinutesSince(route?.latest_received_at || route?.received_at, nowMs);
}

function routeIncludesNode(route, selectedNodeNum = state.selectedNodeNum) {
  if (selectedNodeNum == null) {
    return false;
  }
  const targetNodeNum = Number(selectedNodeNum);
  if (!Number.isFinite(targetNodeNum)) {
    return false;
  }
  const pathNodeNums = Array.isArray(route?.path_node_nums) ? route.path_node_nums : [];
  return pathNodeNums.some((nodeNum) => Number(nodeNum) === targetNodeNum);
}

function routeTargetsNode(route, selectedNodeNum = state.selectedNodeNum) {
  if (selectedNodeNum == null) {
    return false;
  }
  const targetNodeNum = Number(selectedNodeNum);
  if (!Number.isFinite(targetNodeNum)) {
    return false;
  }
  return Number(route?.source_node_num) === targetNodeNum || Number(route?.destination_node_num) === targetNodeNum;
}

function routeSelected(route) {
  return routeTargetsNode(route);
}

function latestRouteFamilies(routes, selectedNodeNum = state.selectedNodeNum) {
  const candidates = [...routes]
    .filter((route) => selectedNodeNum == null || routeTargetsNode(route, selectedNodeNum))
    .sort(compareRoutesByRecency);
  const pairs = new Map();

  candidates.forEach((route) => {
    const pairKey = routePairKey(route) || routeKey(route);
    let bucket = pairs.get(pairKey);
    if (!bucket) {
      bucket = {
        latestSingle: null,
        bestComplete: null,
        families: new Map(),
      };
      pairs.set(pairKey, bucket);
    }

    if (!bucket.latestSingle) {
      bucket.latestSingle = route;
    }

    const familyKey = route?.mesh_packet_id != null
      ? `mesh:${route.mesh_packet_id}`
      : `${pairKey}:${routeSeenAt(route)}`;
    const family = bucket.families.get(familyKey) || { forward: null, return: null };
    if (route?.direction === "forward" && !family.forward) {
      family.forward = route;
    } else if (route?.direction === "return" && !family.return) {
      family.return = route;
    }
    bucket.families.set(familyKey, family);

    if (!bucket.bestComplete && family.forward && family.return) {
      bucket.bestComplete = [family.forward, family.return];
    }
  });

  return [...pairs.values()].flatMap((bucket) => bucket.bestComplete || (bucket.latestSingle ? [bucket.latestSingle] : []));
}

function routeLatLngs(route, nowMs = Date.now()) {
  const points = [];
  for (const nodeNum of route.path_node_nums) {
    const node = nodeByNum(nodeNum);
    if (!nodeHasCoordinates(node) || !nodeIsVisible(node, nowMs)) {
      return null;
    }
    points.push([node.latitude, node.longitude]);
  }
  return points.length >= 2 ? points : null;
}

function activeMeshRoutes(nowMs = Date.now()) {
  if (!state.showRoutes) {
    return [];
  }
  const baseRoutes = state.meshRoutes.routes.filter((route) => routeLatLngs(route, nowMs));
  const routes = baseRoutes.filter((route) => {
    const ageMinutes = routeAgeMinutes(route, nowMs);
    if (ageMinutes == null) {
      return false;
    }
    return ageMinutes <= (routeSelected(route) ? SELECTED_ROUTE_WINDOW_MINUTES : NETWORK_ROUTE_WINDOW_MINUTES);
  });
  return latestRouteFamilies(routes, state.selectedNodeNum);
}

function routeStyle(route, ctx) {
  const overlay = currentThemeOverlay();
  const nowMs = ctx.nowMs;
  const neighborhood = ctx.neighborhood;
  const isSelected = routeSelected(route);
  const routeAge = routeAgeMinutes(route, nowMs);
  const ageRatio = routeAge == null
    ? 1
    : clamp(routeAge / (isSelected ? SELECTED_ROUTE_WINDOW_MINUTES : NETWORK_ROUTE_WINDOW_MINUTES), 0, 1);
  const baseWeight = clamp(1.8 + ((intValue(route.count) - 1) * 0.4), 1.8, 4.2);
  const dimmedRoute = neighborhood != null && !isSelected;
  const baseOpacity = interpolate(ROUTE_MAX_OPACITY, ROUTE_MIN_OPACITY, ageRatio);
  const baseColor = route.direction === "return" ? overlay.routeReturnColor : overlay.routeColor;
  const selectedColor = overlay.preserveRouteColorOnSelect ? baseColor : overlay.routeSelectedColor;
  return {
    color: isSelected ? selectedColor : baseColor,
    weight: isSelected ? Math.min(baseWeight + 1.0, 5.2) : baseWeight,
    opacity: isSelected ? 0.98 : (dimmedRoute ? Math.min(baseOpacity * 0.15, 0.06) : baseOpacity),
    dashArray: route.direction === "return" ? "12 10" : null,
    lineCap: "round",
    lineJoin: "round",
  };
}

function routeSegmentBearing(startLatLng, endLatLng) {
  const start = L.latLng(startLatLng);
  const end = L.latLng(endLatLng);
  const averageLatitudeRadians = ((start.lat + end.lat) / 2) * (Math.PI / 180);
  const deltaLongitude = (end.lng - start.lng) * Math.cos(averageLatitudeRadians);
  const deltaLatitude = end.lat - start.lat;
  if (deltaLongitude === 0 && deltaLatitude === 0) {
    return 0;
  }
  return (Math.atan2(deltaLongitude, deltaLatitude) * 180) / Math.PI;
}

function routeArrowIcon({ color, opacity, weight, bearing }) {
  const overlay = currentThemeOverlay();
  const size = Math.round(clamp(16 + (weight * 2), 18, 24));
  const strokeWidth = Math.max(1.1, Math.min(weight * 0.4, 1.8));
  const arrowFillColor = overlay.routeArrowColor || color;
  const arrowStrokeColor = overlay.routeArrowStrokeColor || "rgba(12, 16, 20, 0.34)";
  const arrowStrokeWidth = arrowStrokeColor === "none" ? 0 : strokeWidth;
  return L.divIcon({
    className: "",
    html: `
      <div
        class="route-arrow-marker"
        style="width:${size}px;height:${size}px;opacity:${clamp(opacity, 0.35, 1).toFixed(3)};transform:rotate(${bearing.toFixed(2)}deg);pointer-events:none;"
      >
        <svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 3 L20 21 L12 16.4 L4 21 Z"
            fill="${arrowFillColor}"
            stroke="${arrowStrokeColor}"
            stroke-width="${arrowStrokeWidth.toFixed(2)}"
            stroke-linejoin="round"
            style="filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.24));"
          ></path>
        </svg>
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function routeArrowPositionFraction(_route) {
  return 0.38;
}

function routeArrowPoint(startLatLng, endLatLng, fraction) {
  return L.latLng(
    startLatLng.lat + ((endLatLng.lat - startLatLng.lat) * fraction),
    startLatLng.lng + ((endLatLng.lng - startLatLng.lng) * fraction),
  );
}

function routeArrowMarkers(_map, route, latLngs, style) {
  if (!routeSelected(route) || !Array.isArray(latLngs) || latLngs.length < 2) {
    return [];
  }

  const markers = [];
  const positionFraction = routeArrowPositionFraction(route);
  for (let index = 0; index < latLngs.length - 1; index += 1) {
    const start = L.latLng(latLngs[index]);
    const end = L.latLng(latLngs[index + 1]);
    if (start.lat === end.lat && start.lng === end.lng) {
      continue;
    }
    const point = routeArrowPoint(start, end, positionFraction);
    markers.push(L.marker(point, {
      icon: routeArrowIcon({
        color: style.color,
        opacity: style.opacity,
        weight: style.weight,
        bearing: routeSegmentBearing(start, end),
      }),
      keyboard: false,
      interactive: false,
      pane: "mesh-route-arrows",
      zIndexOffset: 900,
    }));
  }
  return markers;
}

function nodeFreshness(node) {
  const minutes = ageMinutesSince(node?.last_heard_at);
  if (minutes == null) {
    return "unknown";
  }
  if (minutes <= 60) {
    return "live";
  }
  if (minutes <= 1440) {
    return "warm";
  }
  return "stale";
}

function freshnessRank(node) {
  const freshness = nodeFreshness(node);
  if (freshness === "live") {
    return 3;
  }
  if (freshness === "warm") {
    return 2;
  }
  if (freshness === "stale") {
    return 1;
  }
  return 0;
}

function freshnessLabel(node) {
  const freshness = nodeFreshness(node);
  if (freshness === "live") {
    return t("nodes.freshness.live");
  }
  if (freshness === "warm") {
    return t("nodes.freshness.recent");
  }
  if (freshness === "stale") {
    return t("nodes.freshness.stale");
  }
  return t("nodes.freshness.seen");
}

function sortNodes(items) {
  return [...items].sort((left, right) => {
    const freshnessDelta = freshnessRank(right) - freshnessRank(left);
    if (freshnessDelta !== 0) {
      return freshnessDelta;
    }

    const leftHeard = left.last_heard_at || "";
    const rightHeard = right.last_heard_at || "";
    if (leftHeard !== rightHeard) {
      return rightHeard.localeCompare(leftHeard);
    }

    return left.node_num - right.node_num;
  });
}

function rankRosterNodes(items) {
  return [...items].sort((left, right) => {
    const selectedDelta = Number(right.node_num === state.selectedNodeNum) - Number(left.node_num === state.selectedNodeNum);
    if (selectedDelta !== 0) {
      return selectedDelta;
    }

    const activeDelta = Number(nodeIsActive(right)) - Number(nodeIsActive(left));
    if (activeDelta !== 0) {
      return activeDelta;
    }

    const directDelta = Number(nodeIsDirectRf(right)) - Number(nodeIsDirectRf(left));
    if (directDelta !== 0) {
      return directDelta;
    }

    const activityDelta = nodeActivityCount(right) - nodeActivityCount(left);
    if (activityDelta !== 0) {
      return activityDelta;
    }

    const leftHeard = left.last_heard_at || "";
    const rightHeard = right.last_heard_at || "";
    if (leftHeard !== rightHeard) {
      return rightHeard.localeCompare(leftHeard);
    }

    const staleDelta = Number(nodeIsStale(left)) - Number(nodeIsStale(right));
    if (staleDelta !== 0) {
      return staleDelta;
    }

    const labelDelta = nodeLabel(left).localeCompare(nodeLabel(right), undefined, { sensitivity: "base" });
    if (labelDelta !== 0) {
      return labelDelta;
    }

    return left.node_num - right.node_num;
  });
}

function fromNodeLabel(packet) {
  return nodeLabel(nodeByNum(packet.from_node_num) || {
    node_num: packet.from_node_num,
  });
}

function toNodeLabel(packet) {
  if (packet.to_node_num === BROADCAST_NODE_NUM) {
    return t("common.broadcast");
  }
  const node = nodeByNum(packet.to_node_num);
  return node ? nodeLabel(node) : t("common.nodeWithNum", { num: packet.to_node_num });
}

function intValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, numeric);
}

function sharePercentage(value, total) {
  const normalizedTotal = intValue(total);
  if (!normalizedTotal) {
    return null;
  }
  return Math.round((intValue(value) / normalizedTotal) * 100);
}

function dominantSegment(segments) {
  const ranked = segments
    .map((segment) => ({ ...segment, value: intValue(segment.value) }))
    .filter((segment) => segment.value > 0)
    .sort((left, right) => right.value - left.value);
  return ranked[0] || null;
}

function packetsPerMinute(packetCount, windowMinutes) {
  if (!windowMinutes) {
    return null;
  }
  return intValue(packetCount) / windowMinutes;
}

function percentOf(value, total, digits = 0) {
  const normalizedTotal = Number(total);
  if (!Number.isFinite(normalizedTotal) || normalizedTotal <= 0) {
    return null;
  }
  return Number(((Number(value) / normalizedTotal) * 100).toFixed(digits));
}

function trendMeta(current, previous, digits = 0, suffix = "") {
  const currentValue = Number(current);
  const previousValue = Number(previous);
  if (!Number.isFinite(currentValue) || !Number.isFinite(previousValue)) {
    return { tone: "none", symbol: "—", detail: t("common.noBaseline") };
  }
  const delta = currentValue - previousValue;
  if (Math.abs(delta) < 0.0001) {
    return { tone: "flat", symbol: "→", detail: t("common.flat") };
  }
  return {
    tone: delta > 0 ? "up" : "down",
    symbol: delta > 0 ? "↑" : "↓",
    detail: formatCompactChange(delta, digits, suffix),
  };
}

function trendContextCopy(trend, context = "") {
  if (!trend) {
    return "";
  }
  if (trend.tone === "none") {
    return t("common.noBaseline");
  }
  if (trend.tone === "flat") {
    return context ? t("trend.flatVsPrior", { context }) : t("common.flat");
  }
  return context ? t("trend.valueVsPrior", { detail: trend.detail, context }) : trend.detail;
}

function freshestObservationAgeMinutes(summary, nowMs = Date.now()) {
  const candidates = [
    ageMinutesSince(state.lastPacketReceivedAt, nowMs),
    ageMinutesSince(summary?.receiver?.updated_at, nowMs),
  ].filter((value) => value != null);
  if (!candidates.length) {
    return null;
  }
  return Math.min(...candidates);
}

function pathHeadline({ packetCount, directShare, relayShare, mqttShare }) {
  if (!packetCount) {
    return t("signals.path.noFreshRead");
  }
  if (mqttShare != null && mqttShare >= 30) {
    return t("signals.path.mqttHeavy");
  }
  if (relayShare != null && relayShare >= 40) {
    return t("signals.path.relayHeavy");
  }
  if (directShare != null && relayShare != null && directShare >= 55 && directShare >= (relayShare + 10)) {
    return t("signals.path.mostlyDirect");
  }
  return t("signals.path.mixed");
}

function refreshKpiTicker() {
  renderKpiTicker(state.meshSummary);
}

function renderKpiTicker(summary) {
  renderConnectionIndicator();

  if (!statsRow || !summary) {
    return;
  }

  const nodes = summary?.nodes || {};
  const traffic = summary?.traffic || {};
  const currentWindow = summary?.windowed_activity?.current || null;
  const windowMinutes = Number(summary?.windowed_activity?.window_minutes) || DEFAULT_RECENT_ACTIVITY_WINDOW_MINUTES;
  const totalNodes = intValue(nodes.total);
  const activeNodes3h = intValue(nodes.active_3h);
  const currentPacketCount = intValue(currentWindow?.packet_count);
  const currentPacketsRate = packetsPerMinute(currentPacketCount, windowMinutes);
  const meshPaths = Number.isFinite(Number(state.drawnRouteCount))
    ? intValue(state.drawnRouteCount)
    : null;

  const statNodes = statsRow.querySelector("#stat-nodes .stat-value");
  const statActive = statsRow.querySelector("#stat-active .stat-value");
  const statTraffic = statsRow.querySelector("#stat-traffic .stat-value");
  const statPaths = statsRow.querySelector("#stat-paths .stat-value");

  if (statNodes) {
    statNodes.textContent = formatWholeNumber(totalNodes);
  }
  if (statActive) {
    statActive.textContent = formatWholeNumber(activeNodes3h);
  }
  if (statTraffic) {
    statTraffic.textContent = currentPacketCount ? formatNumber(currentPacketsRate, 1) : "--";
  }
  if (statPaths) {
    statPaths.textContent = meshPaths == null ? "--" : formatWholeNumber(meshPaths);
  }
}

function intelStat(label, value, detail, tone = "") {
  return `
    <article class="intel-stat${tone ? ` ${tone}` : ""}">
      <strong class="intel-stat-value">${escapeHtml(value)}</strong>
      <span class="intel-stat-label">${escapeHtml(label)}</span>
      <span class="intel-stat-detail">${escapeHtml(detail)}</span>
    </article>
  `;
}

function intelMeter(title, headline, segments, emptyLabel = t("signals.noPassiveTraffic")) {
  const normalized = segments
    .map((segment) => ({ ...segment, value: intValue(segment.value) }))
    .filter((segment) => segment.value > 0);
  const total = normalized.reduce((sum, segment) => sum + segment.value, 0);

  return `
    <article class="intel-story-card">
      <div class="intel-story-head">
        <div>
          <p class="intel-story-kicker">${escapeHtml(title)}</p>
          <h3>${escapeHtml(headline)}</h3>
        </div>
        <span class="mono-text">${escapeHtml(total ? t("common.total", { count: formatWholeNumber(total) }) : t("common.waiting"))}</span>
      </div>
      ${total ? `
        <div class="intel-meter">
          ${normalized.map((segment) => `
            <span
              class="intel-meter-segment ${segment.tone}"
              style="flex:${segment.value}"
              title="${escapeHtml(`${segment.label}: ${formatWholeNumber(segment.value)} (${sharePercentage(segment.value, total)}%)`)}"
            ></span>
          `).join("")}
        </div>
        <div class="intel-meter-legend">
          ${normalized.map((segment) => `
            <div class="intel-meter-key">
              <span class="intel-meter-key-label">
                <span class="intel-meter-dot ${segment.tone}"></span>
                ${escapeHtml(segment.label)}
              </span>
              <span class="mono-text">${escapeHtml(`${sharePercentage(segment.value, total)}%`)}</span>
            </div>
          `).join("")}
        </div>
      ` : `
        <div class="hud-empty compact">
          <p>${escapeHtml(emptyLabel)}</p>
        </div>
      `}
    </article>
  `;
}

function routingHealthRow(label, value) {
  return `
    <div class="routing-health-row">
      <span class="routing-health-label">${escapeHtml(label)}</span>
      <span class="routing-health-value">${escapeHtml(value)}</span>
    </div>
  `;
}

function packetBreakdownRow(item, totalPackets) {
  const value = intValue(item?.value);
  const pct = totalPackets > 0 ? Math.round((value / totalPackets) * 100) : 0;
  const barPct = totalPackets > 0 ? (value / totalPackets) * 100 : 0;
  const title = `${item.label}: ${formatWholeNumber(value)} (${pct}%)`;
  return `
    <div class="breakdown-row" title="${escapeHtml(title)}">
      <span class="breakdown-label">${escapeHtml(item.label)}</span>
      <span class="breakdown-bar"><span class="breakdown-bar-fill ${item.tone}" style="width:${barPct}%"></span></span>
      <span class="breakdown-count mono-text">${formatWholeNumber(value)}</span>
      <span class="breakdown-pct mono-text">${pct}%</span>
    </div>
  `;
}

function stackedBarSegmentsMarkup(items, totalPackets) {
  if (!(totalPackets > 0)) {
    return `<span class="routing-health-stacked-empty"></span>`;
  }
  return items.map((item) => {
    const value = intValue(item?.value);
    if (value <= 0) {
      return "";
    }
    const pct = Math.round((value / totalPackets) * 100);
    const title = `${item.label}: ${formatWholeNumber(value)} (${pct}%)`;
    return `
      <span
        class="routing-health-stacked-segment ${item.tone}"
        style="width:${(value / totalPackets) * 100}%"
        title="${escapeHtml(title)}"
      ></span>
    `;
  }).join("");
}

function receiverMetricDetail(receiver) {
  if (!receiver || receiver.node_num == null) {
    return t("signals.receiverIdentityWaiting");
  }
  if (receiver.updated_at) {
    return `${receiver.label || t("common.nodeWithNum", { num: receiver.node_num })} · ${formatTime(receiver.updated_at)}`;
  }
  return `${receiver.label || t("common.nodeWithNum", { num: receiver.node_num })} · ${t("signals.telemetryPending")}`;
}

function receiverHistorySeries(receiver, key) {
  if (!Array.isArray(receiver?.history)) {
    return [];
  }
  return receiver.history
    .map((sample) => ({
      recorded_at: sample?.recorded_at || null,
      value: Number(sample?.[key]),
    }))
    .filter((sample) => sample.recorded_at && Number.isFinite(sample.value));
}

function dailyTotalsHistorySeries(summary, valueSelector, windowDays = DAILY_HEARD_NODES_WINDOW_DAYS) {
  const rawItems = Array.isArray(summary?.nodes?.daily_totals) ? summary.nodes.daily_totals : [];
  const valuesByDay = new Map();
  let anchorValue = null;
  const now = new Date();
  const endDate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const startDate = shiftUtcDays(endDate, -(Math.max(windowDays, 1) - 1));
  const startDay = utcDayKey(startDate);

  rawItems.forEach((item) => {
    const day = typeof item?.day === "string" ? item.day : null;
    const value = Number(valueSelector(item));
    if (!day || !Number.isFinite(value)) {
      return;
    }
    if (day < startDay) {
      anchorValue = value;
      return;
    }
    valuesByDay.set(day, value);
  });

  const series = [];
  let lastValue = anchorValue;
  let seenValue = anchorValue != null;

  for (let index = 0; index < windowDays; index += 1) {
    const day = utcDayKey(shiftUtcDays(startDate, index));
    if (!day) {
      continue;
    }
    if (valuesByDay.has(day)) {
      lastValue = valuesByDay.get(day);
      seenValue = true;
    }
    series.push({
      day,
      value: seenValue ? lastValue : null,
    });
  }

  return series;
}

function heardNodesHistorySeries(summary, windowDays = DAILY_HEARD_NODES_WINDOW_DAYS) {
  return dailyTotalsHistorySeries(summary, (item) => item?.total, windowDays);
}

function coverageHistorySeries(summary, windowDays = DAILY_HEARD_NODES_WINDOW_DAYS) {
  return dailyTotalsHistorySeries(
    summary,
    (item) => sharePercentage(item?.mapped, item?.total),
    windowDays,
  );
}

function sparklineGeometry(series, width = 212, height = 54, padding = 4) {
  if (!series.length) {
    return null;
  }

  const validSamples = series
    .map((sample, index) => ({
      index,
      value: Number(sample?.value),
    }))
    .filter((sample) => Number.isFinite(sample.value));

  if (!validSamples.length) {
    return null;
  }

  const values = validSamples.map((sample) => sample.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue;
  const innerWidth = width - (padding * 2);
  const innerHeight = height - (padding * 2);
  const baselineY = height - padding;
  const denominator = Math.max(series.length - 1, 1);

  const pointForSample = (sample) => {
    const x = padding + ((innerWidth * sample.index) / denominator);
    const y = range === 0
      ? padding + (innerHeight / 2)
      : padding + (((maxValue - sample.value) / range) * innerHeight);
    return { x, y };
  };

  const points = validSamples.map(pointForSample);

  if (points.length === 1) {
    const soloY = points[0].y;
    const linePath = `M ${padding.toFixed(2)} ${soloY.toFixed(2)} L ${(width - padding).toFixed(2)} ${soloY.toFixed(2)}`;
    const areaPath = `${linePath} L ${(width - padding).toFixed(2)} ${baselineY.toFixed(2)} L ${padding.toFixed(2)} ${baselineY.toFixed(2)} Z`;
    return {
      areaPath,
      linePath,
      lastX: (width - padding).toFixed(2),
      lastY: soloY.toFixed(2),
      minValue,
      maxValue,
    };
  }

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const areaPath = `${linePath} L ${last.x.toFixed(2)} ${baselineY.toFixed(2)} L ${first.x.toFixed(2)} ${baselineY.toFixed(2)} Z`;

  return {
    areaPath,
    linePath,
    lastX: last.x.toFixed(2),
    lastY: last.y.toFixed(2),
    minValue,
    maxValue,
  };
}

function receiverSparkline(label, tone, series) {
  const ariaLabel = tone === "channel"
    ? t("signals.heardNodesHistory")
    : (tone === "coverage" ? t("signals.coverageHistory") : t("common.historyFor", { label }));
  return singleSeriesAxisSparkline(series, {
    ariaLabel,
    frameClass: `${tone} detailed`,
    formatXLabel: (sample) => formatSparklineDay(sample?.day),
    yLabelSuffix: tone === "coverage" ? "%" : "",
  });
}

function receiverTelemetryPanel(label, currentValue, key, tone, receiver) {
  const series = receiverHistorySeries(receiver, key);
  const geometry = sparklineGeometry(series);
  const peakValue = geometry ? formatNumber(geometry.maxValue, 1, "%") : null;
  const sampleLabel = series.length === 1 ? t("common.sample") : t("common.samples");
  const meta = peakValue
    ? t("signals.peakSamples", { peak: peakValue, count: formatWholeNumber(series.length), sampleLabel })
    : "";
  const ariaLabel = t("common.historyFor", { label });

  return `
    <section class="receiver-metric ${tone}">
      <span class="receiver-metric-label">${escapeHtml(label)}</span>
      <strong class="receiver-metric-value">${escapeHtml(formatNumber(currentValue, 1, "%"))}</strong>
      ${meta ? `<span class="receiver-metric-meta mono-text">${escapeHtml(meta)}</span>` : ""}
      ${singleSeriesAxisSparkline(series, {
        ariaLabel,
        frameClass: `${tone} detailed`,
        formatXLabel: (sample) => formatSparklineTime(sample?.recorded_at),
        yLabelSuffix: "%",
      })}
    </section>
  `;
}

function heardNodesPanel(totalNodes, summary) {
  const series = heardNodesHistorySeries(summary);
  const sparkline = receiverSparkline(t("signals.heardNodes"), "channel", series);

  return `
    <section class="receiver-metric heard-nodes-card channel">
      <span class="receiver-metric-label">${escapeHtml(t("signals.heardNodes"))}</span>
      <strong class="receiver-metric-value">${escapeHtml(formatWholeNumber(totalNodes))}</strong>
      ${sparkline}
    </section>
  `;
}

function coveragePanel(mappedNodes, totalNodes, summary) {
  const coverageValue = sharePercentage(mappedNodes, totalNodes);
  const series = coverageHistorySeries(summary);
  const sparkline = receiverSparkline(t("signals.coverage"), "coverage", series);
  const detail = totalNodes
    ? t("signals.coverageDetail", { mapped: formatWholeNumber(mappedNodes), total: formatWholeNumber(totalNodes) })
    : t("signals.noNodeRoster");

  return `
    <section class="receiver-metric coverage-card coverage">
      <span class="receiver-metric-label">${escapeHtml(t("signals.coverage"))}</span>
      <strong class="receiver-metric-value">${escapeHtml(coverageValue == null ? "—" : `${coverageValue}%`)}</strong>
      <span class="receiver-metric-meta mono-text">${escapeHtml(detail)}</span>
      ${sparkline}
    </section>
  `;
}

function channelUtilizationBlock(receiver) {
  const recLabel = receiver?.label || (receiver?.node_num != null ? t("common.nodeWithNum", { num: receiver.node_num }) : null);
  const recTime = receiver?.updated_at ? formatTime(receiver.updated_at) : null;
  const sectionParts = [t("signals.channelUtilization")];
  if (recLabel) sectionParts.push(recLabel);
  if (recTime) sectionParts.push(recTime);

  return `
    <div class="signals-section">
      <span class="signals-section-label">${escapeHtml(sectionParts.join(" · "))}</span>
      <div class="receiver-metric-grid">
        ${receiverTelemetryPanel(t("signals.chUtil"), receiver?.channel_utilization, "channel_utilization", "channel", receiver)}
        ${receiverTelemetryPanel(t("signals.airUtilTx"), receiver?.air_util_tx, "air_util_tx", "air", receiver)}
      </div>
    </div>
  `;
}

function metric(label, value, tone = "", detail = "") {
  return `
    <div class="hud-metric${tone ? ` ${tone}` : ""}">
      <span class="hud-metric-label">${escapeHtml(label)}</span>
      <span class="hud-metric-value">${escapeHtml(value)}</span>
      ${detail ? `<span class="hud-metric-detail">${escapeHtml(detail)}</span>` : ""}
    </div>
  `;
}

function snrHistorySeries(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      timestamp: item?.received_at || null,
      value: Number(item?.rx_snr),
    }))
    .filter((sample) => Number.isFinite(sample.value))
    .sort((left, right) => {
      const leftMs = Date.parse(left.timestamp || "");
      const rightMs = Date.parse(right.timestamp || "");
      if (Number.isNaN(leftMs) && Number.isNaN(rightMs)) {
        return 0;
      }
      if (Number.isNaN(leftMs)) {
        return 1;
      }
      if (Number.isNaN(rightMs)) {
        return -1;
      }
      return leftMs - rightMs;
    });
}

function formatSparklineTime(value) {
  if (!value) {
    return t("common.na");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return t("common.na");
  }
  return new Intl.DateTimeFormat(currentIntlLocale(), {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatSparklineDay(value) {
  if (!value) {
    return t("common.na");
  }
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return t("common.na");
  }
  return new Intl.DateTimeFormat(currentIntlLocale(), {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function sparklineTickIndexes(length, maxTicks = 3) {
  if (length <= 0) {
    return [];
  }
  if (length === 1 || maxTicks <= 1) {
    return [0];
  }
  if (length === 2 || maxTicks === 2) {
    return [0, length - 1];
  }
  const indexes = [0, Math.round((length - 1) / 2), length - 1];
  return [...new Set(indexes)];
}

function sparklineYTicks(geometry, height = 54, padding = 4) {
  if (!geometry) {
    return [];
  }
  const min = Number(geometry.minValue);
  const max = Number(geometry.maxValue);
  const innerHeight = height - (padding * 2);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [];
  }
  if (min === max) {
    return [{
      label: formatNumber(max, 1, ""),
      y: padding + (innerHeight / 2),
    }];
  }
  const mid = min + ((max - min) / 2);
  return [
    { label: formatNumber(max, 1, ""), y: padding },
    { label: formatNumber(mid, 1, ""), y: padding + (innerHeight / 2) },
    { label: formatNumber(min, 1, ""), y: height - padding },
  ];
}

function sparklinePaths(geometry, values) {
  if (!geometry || !Array.isArray(values) || !values.length) {
    return null;
  }
  const min = Number(geometry.minValue);
  const max = Number(geometry.maxValue);
  const innerWidth = 212 - 8;
  const innerHeight = 54 - 8;
  const denominator = Math.max(values.length - 1, 1);
  const range = max - min;
  const points = values.map((value, index) => {
    const x = 4 + ((innerWidth * index) / denominator);
    const y = range === 0
      ? 4 + (innerHeight / 2)
      : 4 + (((max - value) / range) * innerHeight);
    return { x, y };
  });
  if (!points.length) {
    return null;
  }
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const last = points[points.length - 1];
  return {
    path,
    lastX: last.x.toFixed(2),
    lastY: last.y.toFixed(2),
  };
}

function renderAxisSparkline(frameClass, ariaLabel, xTicks, yTicks, yLabelSuffix, content) {
  const classes = ["receiver-sparkline-frame", frameClass].filter(Boolean).join(" ");
  return `
    <div class="${classes}">
      <div class="sparkline-chart-grid">
        <div class="sparkline-y-axis mono-text" aria-hidden="true">
          ${yTicks.map((tick) => `<span>${escapeHtml(`${tick.label}${yLabelSuffix}`)}</span>`).join("")}
        </div>
        <div class="sparkline-plot">
          <svg
            class="receiver-sparkline-graphic"
            viewBox="0 0 212 54"
            aria-label="${escapeHtml(ariaLabel)}"
            role="img"
          >
            ${yTicks.map((tick) => `
              <line
                class="receiver-sparkline-guide"
                x1="4"
                x2="208"
                y1="${Number(tick.y).toFixed(2)}"
                y2="${Number(tick.y).toFixed(2)}"
              ></line>
            `).join("")}
            ${content}
          </svg>
        </div>
      </div>
      <div class="sparkline-x-axis mono-text" aria-hidden="true">
        ${xTicks.map((tick) => `
          <span class="sparkline-x-tick">
            <span class="sparkline-x-notch"></span>
            <span>${escapeHtml(tick.label)}</span>
          </span>
        `).join("")}
      </div>
    </div>
  `;
}

function singleSeriesAxisSparkline(series, options = {}) {
  if (!series.length) {
    return "";
  }

  const geometry = sparklineGeometry(series);
  if (!geometry) {
    return "";
  }

  const {
    ariaLabel,
    frameClass = "",
    formatXLabel = (sample) => formatSparklineTime(sample?.timestamp),
    yLabelSuffix = "",
  } = options;
  const xTicks = sparklineTickIndexes(series.length, 3).map((index) => ({
    index,
    label: formatXLabel(series[index]),
  }));
  const yTicks = sparklineYTicks(geometry);

  return renderAxisSparkline(
    frameClass,
    ariaLabel,
    xTicks,
    yTicks,
    yLabelSuffix,
    `
      <path class="receiver-sparkline-area" d="${geometry.areaPath}"></path>
      <path class="receiver-sparkline-line" d="${geometry.linePath}"></path>
      <circle class="receiver-sparkline-dot" cx="${geometry.lastX}" cy="${geometry.lastY}" r="3.5"></circle>
    `,
  );
}

function nodeSnrSparkline(series) {
  if (!series.length) {
    return "";
  }

  const geometry = sparklineGeometry(series);
  if (!geometry) {
    return "";
  }

  const xTicks = sparklineTickIndexes(series.length, 3).map((index) => ({
    index,
    label: formatSparklineTime(series[index]?.timestamp),
  }));
  const yTicks = sparklineYTicks(geometry);

  return `
    <div class="receiver-sparkline-frame channel detailed">
      <div class="sparkline-chart-grid">
        <div class="sparkline-y-axis mono-text" aria-hidden="true">
          ${yTicks.map((tick) => `<span>${escapeHtml(tick.label)}</span>`).join("")}
        </div>
        <div class="sparkline-plot">
          <svg
            class="receiver-sparkline-graphic"
            viewBox="0 0 212 54"
            aria-label="${escapeHtml(t("nodes.snrHistory"))}"
            role="img"
          >
            ${yTicks.map((tick) => `
              <line
                class="receiver-sparkline-guide"
                x1="4"
                x2="208"
                y1="${Number(tick.y).toFixed(2)}"
                y2="${Number(tick.y).toFixed(2)}"
              ></line>
            `).join("")}
            <path class="receiver-sparkline-area" d="${geometry.areaPath}"></path>
            <path class="receiver-sparkline-line" d="${geometry.linePath}"></path>
            <circle class="receiver-sparkline-dot" cx="${geometry.lastX}" cy="${geometry.lastY}" r="3.5"></circle>
          </svg>
        </div>
      </div>
      <div class="sparkline-x-axis mono-text" aria-hidden="true">
        ${xTicks.map((tick) => `
          <span class="sparkline-x-tick">
            <span class="sparkline-x-notch"></span>
            <span>${escapeHtml(tick.label)}</span>
          </span>
        `).join("")}
      </div>
    </div>
  `;
}

function nodeSnrDetail(insights) {
  const min = formatNumber(insights?.worst_rx_snr, 1, "");
  const max = formatNumber(insights?.best_rx_snr, 1, "");
  const avg = formatNumber(insights?.avg_rx_snr, 1, "");
  return t("nodes.snrDetail", { min, max, avg });
}

function nodeMetricHistorySeries(items, key) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      timestamp: item?.recorded_at || null,
      value: Number(item?.[key]),
    }))
    .filter((sample) => Number.isFinite(sample.value))
    .sort((left, right) => {
      const leftMs = Date.parse(left.timestamp || "");
      const rightMs = Date.parse(right.timestamp || "");
      if (Number.isNaN(leftMs) && Number.isNaN(rightMs)) {
        return 0;
      }
      if (Number.isNaN(leftMs)) {
        return 1;
      }
      if (Number.isNaN(rightMs)) {
        return -1;
      }
      return leftMs - rightMs;
    });
}

function nodeMetricHistorySamples(node, metricHistory) {
  if (Array.isArray(metricHistory) && metricHistory.length) {
    return metricHistory;
  }
  if (node?.updated_at && (Number.isFinite(Number(node?.channel_utilization)) || Number.isFinite(Number(node?.air_util_tx)))) {
    return [{
      recorded_at: node.updated_at,
      channel_utilization: node.channel_utilization,
      air_util_tx: node.air_util_tx,
    }];
  }
  return [];
}

function nodeUtilizationSparkline(metricHistory) {
  const channelSeries = nodeMetricHistorySeries(metricHistory, "channel_utilization");
  const airSeries = nodeMetricHistorySeries(metricHistory, "air_util_tx");
  const indexTimestampMap = new Map();
  channelSeries.forEach((sample) => {
    if (sample.timestamp) {
      indexTimestampMap.set(sample.timestamp, { timestamp: sample.timestamp });
    }
  });
  airSeries.forEach((sample) => {
    if (sample.timestamp) {
      indexTimestampMap.set(sample.timestamp, { timestamp: sample.timestamp });
    }
  });
  const mergedSeries = [...indexTimestampMap.values()]
    .sort((left, right) => Date.parse(left.timestamp || "") - Date.parse(right.timestamp || ""))
    .map((sample) => ({
      timestamp: sample.timestamp,
      channel: channelSeries.find((item) => item.timestamp === sample.timestamp)?.value,
      air: airSeries.find((item) => item.timestamp === sample.timestamp)?.value,
    }))
    .filter((sample) => Number.isFinite(sample.channel) || Number.isFinite(sample.air));
  if (!mergedSeries.length) {
    return "";
  }

  const allValues = mergedSeries.flatMap((sample) => [sample.channel, sample.air]).filter(Number.isFinite);
  const indexedValues = allValues.map((value, index) => ({ value, index }));
  const geometry = sparklineGeometry(indexedValues);
  if (!geometry) {
    return "";
  }

  const xTicks = sparklineTickIndexes(mergedSeries.length, 2).map((index) => ({
    index,
    label: formatSparklineTime(mergedSeries[index]?.timestamp),
  }));
  const yTicks = sparklineYTicks(geometry);
  const channelValues = mergedSeries.map((sample) => Number.isFinite(sample.channel) ? sample.channel : 0);
  const airValues = mergedSeries.map((sample) => Number.isFinite(sample.air) ? sample.air : 0);
  const channelPaths = sparklinePaths(geometry, channelValues);
  const airPaths = sparklinePaths(geometry, airValues);

  return `
    <div class="receiver-sparkline-frame detailed dual">
      <div class="sparkline-chart-grid">
        <div class="sparkline-y-axis mono-text" aria-hidden="true">
          ${yTicks.map((tick) => `<span>${escapeHtml(`${tick.label}%`)}</span>`).join("")}
        </div>
        <div class="sparkline-plot">
          <svg
            class="receiver-sparkline-graphic"
            viewBox="0 0 212 54"
            aria-label="${escapeHtml(t("nodes.utilHistory"))}"
            role="img"
          >
            ${yTicks.map((tick) => `
              <line
                class="receiver-sparkline-guide"
                x1="4"
                x2="208"
                y1="${Number(tick.y).toFixed(2)}"
                y2="${Number(tick.y).toFixed(2)}"
              ></line>
            `).join("")}
            ${channelPaths ? `<path class="receiver-sparkline-line dual-channel" d="${channelPaths.path}"></path>` : ""}
            ${airPaths ? `<path class="receiver-sparkline-line dual-air" d="${airPaths.path}"></path>` : ""}
            ${channelPaths ? `<circle class="receiver-sparkline-dot dual-channel" cx="${channelPaths.lastX}" cy="${channelPaths.lastY}" r="3.2"></circle>` : ""}
            ${airPaths ? `<circle class="receiver-sparkline-dot dual-air" cx="${airPaths.lastX}" cy="${airPaths.lastY}" r="3.2"></circle>` : ""}
          </svg>
        </div>
      </div>
      <div class="sparkline-x-axis mono-text" aria-hidden="true">
        ${xTicks.map((tick) => `
          <span class="sparkline-x-tick">
            <span class="sparkline-x-notch"></span>
            <span>${escapeHtml(tick.label)}</span>
          </span>
        `).join("")}
      </div>
    </div>
  `;
}

function nodeUtilizationCard(node, metricHistory, freshness) {
  const samples = nodeMetricHistorySamples(node, metricHistory);
  const sparkline = nodeUtilizationSparkline(samples);
  const chUtil = formatNumber(node?.channel_utilization, 1, "%");
  const airUtil = formatNumber(node?.air_util_tx, 1, "%");
  return `
    <div class="hud-metric util-card${freshness === "stale" ? " muted" : ""}">
      <div class="hud-metric-dual-head">
        <span class="hud-metric-label">${escapeHtml(t("nodes.utilLabel"))}</span>
        <span class="hud-metric-inline hud-metric-inline-legend mono-text">
          <span class="hud-inline-series hud-inline-series--channel">
            <span class="hud-inline-series-dot" aria-hidden="true"></span>
            <span class="hud-inline-series-label">${escapeHtml(t("signals.chUtil"))}</span>
            <span class="hud-inline-series-value">${escapeHtml(chUtil)}</span>
          </span>
          <span class="hud-inline-series hud-inline-series--air">
            <span class="hud-inline-series-dot" aria-hidden="true"></span>
            <span class="hud-inline-series-label">${escapeHtml(t("signals.airUtilTx"))}</span>
            <span class="hud-inline-series-value">${escapeHtml(airUtil)}</span>
          </span>
        </span>
      </div>
      ${sparkline}
      <span class="hud-metric-meta mono-text">${escapeHtml(t("nodes.samples", { count: formatWholeNumber(samples.length) }))}</span>
    </div>
  `;
}

function nodePacketBreakdownCard(insights) {
  const sentPackets = Math.max(0, intValue(insights?.sent_packets ?? insights?.heard_packets));
  const routingTypes = [
    { label: t("path.direct"), value: intValue(insights?.direct_packets), tone: "direct" },
    { label: t("path.relayed"), value: intValue(insights?.relayed_packets), tone: "relayed" },
    { label: t("path.mqtt"), value: intValue(insights?.mqtt_packets), tone: "mqtt" },
  ];
  const textPackets = intValue(insights?.text_packets);
  const positionPackets = intValue(insights?.position_packets);
  const telemetryPackets = intValue(insights?.telemetry_packets);
  const breakdown = [
    { label: t("signals.packetType.text"), value: textPackets, tone: "text" },
    { label: t("signals.packetType.telemetry"), value: telemetryPackets, tone: "telemetry" },
    { label: t("signals.packetType.position"), value: positionPackets, tone: "position" },
    {
      label: t("signals.packetType.other"),
      value: Math.max(0, sentPackets - textPackets - telemetryPackets - positionPackets),
      tone: "other",
    },
  ];
  return `
    <div class="hud-metric breakdown-card">
      <span class="hud-metric-label">${escapeHtml(t("signals.routingHealth"))}</span>
      <div class="routing-health-stacked" title="${escapeHtml(t("signals.routingHealth"))}">
        ${stackedBarSegmentsMarkup(routingTypes, sentPackets)}
      </div>
      <div class="routing-health-stacked-legend">
        ${routingTypes.map((item) => `
          <span class="routing-health-stacked-key">
            <span class="breakdown-bar-fill ${item.tone}" aria-hidden="true"></span>
            <span>${escapeHtml(item.label)}</span>
            <span class="mono-text">${escapeHtml(`${sentPackets > 0 ? Math.round((item.value / sentPackets) * 100) : 0}%`)}</span>
          </span>
        `).join("")}
      </div>
      ${routingHealthRow(t("signals.totalPackets"), formatWholeNumber(sentPackets))}
      <span class="hud-metric-label">${escapeHtml(t("nodes.packetBreakdown"))}</span>
      <div class="packet-breakdown">
        ${breakdown.map((item) => packetBreakdownRow(item, sentPackets)).join("")}
      </div>
    </div>
  `;
}

function nodeSnrCard(node, insights, recentPackets, freshness) {
  const sparkline = nodeSnrSparkline(snrHistorySeries(recentPackets));
  return `
    <div class="hud-metric snr-card${freshness === "stale" ? " muted" : ""}">
      <span class="hud-metric-label">SNR</span>
      <span class="hud-metric-value">${escapeHtml(formatNumber(node?.last_snr, 1, " dB"))}</span>
      ${sparkline}
      <span class="hud-metric-meta mono-text">${escapeHtml(nodeSnrDetail(insights))}</span>
    </div>
  `;
}

function quantile(values, ratio) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = (sorted.length - 1) * ratio;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) {
    return sorted[lower];
  }
  const weight = index - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function focusNodes(items) {
  if (items.length <= 12) {
    return items;
  }

  const latLower = quantile(items.map((node) => node.latitude), 0.08);
  const latUpper = quantile(items.map((node) => node.latitude), 0.92);
  const lonLower = quantile(items.map((node) => node.longitude), 0.08);
  const lonUpper = quantile(items.map((node) => node.longitude), 0.92);

  const focus = items.filter((node) => (
    node.latitude >= latLower
    && node.latitude <= latUpper
    && node.longitude >= lonLower
    && node.longitude <= lonUpper
  ));

  return focus.length >= 12 ? focus : items;
}

function ensureSelectedNode() {
  if (state.selectedNodeNum != null && !nodeByNum(state.selectedNodeNum)) {
    state.selectedNodeNum = null;
  }
}

function receiverLinkActive() {
  return state.socketState === "live" && state.collectorStatus?.connected !== false;
}

function meshIsStale() {
  const age = freshestObservationAgeMinutes(state.meshSummary);
  return age == null || age > KPI_STALE_WINDOW_MINUTES;
}

function connectionVisualState() {
  if (receiverLinkActive()) {
    return meshIsStale() ? "degraded" : "online";
  }
  if (state.socketState === "connecting" || state.socketState === "reconnecting") {
    return "degraded";
  }
  if (state.socketState === "error" && state.collectorStatus?.connected !== false) {
    return "degraded";
  }
  return "offline";
}

function connectionStateTitle() {
  if (receiverLinkActive()) {
    return meshIsStale() ? t("status.stale") : t("status.live");
  }
  if (state.socketState === "connecting") {
    return t("status.connecting");
  }
  if (state.socketState === "reconnecting") {
    return t("status.reconnecting");
  }
  if (state.socketState === "blocked") {
    return t("status.blocked");
  }
  if (state.collectorStatus && !state.collectorStatus.connected) {
    return t("status.offline");
  }
  if (state.socketState === "error") {
    return t("status.degraded");
  }
  return t("status.offline");
}

function localizedCollectorStatusDetail(detail) {
  if (typeof detail !== "string" || !detail.trim()) {
    return "";
  }
  const normalized = detail.trim().toLowerCase();
  if (normalized === "connection lost") {
    return t("status.detail.connectionLost");
  }
  if (normalized === "demo dataset loaded for headless preview") {
    return t("status.detail.demoLoaded");
  }
  if (normalized === "missing radio") {
    return t("status.detail.missingRadio");
  }
  return detail;
}

function connectionStateDetail() {
  const updatedText = state.lastUpdatedAt
    ? t("status.lastUpdate", { time: formatLastUpdated(state.lastUpdatedAt) })
    : t("status.noLiveUpdates");
  const packetText = state.lastPacketReceivedAt
    ? t("status.lastPacket", { time: formatTime(state.lastPacketReceivedAt) })
    : t("status.noPacketsHeard");

  if (receiverLinkActive()) {
    if (meshIsStale()) {
      return t("status.linkActiveStale", { packet: packetText, updated: updatedText });
    }
    return t("status.linkActive", { packet: packetText, updated: updatedText });
  }

  if (state.collectorStatus?.detail) {
    return `${localizedCollectorStatusDetail(state.collectorStatus.detail)}. ${packetText}. ${updatedText}.`;
  }

  if (state.collectorStatus && !state.collectorStatus.connected) {
    return t("status.linkUnavailable", { packet: packetText, updated: updatedText });
  }

  if (state.socketState === "reconnecting") {
    return t("status.streamReconnecting", { packet: packetText, updated: updatedText });
  }

  if (state.socketState === "connecting") {
    return t("status.streamOpening", { packet: packetText, updated: updatedText });
  }

  if (state.socketState === "blocked") {
    return t("status.streamBlocked", { packet: packetText, updated: updatedText });
  }

  if (state.socketState === "error") {
    return t("status.streamError", { packet: packetText, updated: updatedText });
  }

  return t("status.waitingForReceiver", { packet: packetText, updated: updatedText });
}

function renderPerspectiveLabel() {
  if (!perspectiveLabel) {
    return;
  }
  if (!state.perspective) {
    perspectiveLabel.textContent = t("status.receiverPending");
    return;
  }
  const label = state.perspective.label || t("status.receiver");
  const localNodeNum = state.perspective.local_node_num;
  perspectiveLabel.textContent = localNodeNum == null
    ? label
    : `${label} · RX ${localNodeNum}`;
}

function chatChannelName() {
  const channelName = state.perspective?.channel_name;
  return typeof channelName === "string" && channelName.trim() ? channelName.trim() : null;
}

function channelScopedText(defaultKey, withChannelKey) {
  const channelName = chatChannelName();
  if (channelName) {
    return t(withChannelKey, { channel: channelName });
  }
  return t(defaultKey);
}

function renderDocumentTitle() {
  document.title = channelScopedText("document.title", "document.titleWithChannel");
}

function renderMapLabels() {
  if (mapRoot) {
    mapRoot.setAttribute("aria-label", channelScopedText("map.nodeMap", "map.nodeMapWithChannel"));
  }
}

function renderChatPanelSubtitle() {
  if (!chatPanelSubtitle) {
    return;
  }
  const channelName = chatChannelName();
  chatPanelSubtitle.textContent = channelName
    ? `${t("common.broadcast")} · ${channelName}`
    : t("common.broadcast");
}

function renderChannelScopedUi() {
  renderDocumentTitle();
  renderMapLabels();
  renderChatPanelSubtitle();
}

function renderConnectionIndicator() {
  const title = connectionStateTitle();
  const detail = connectionStateDetail();
  collectorCard.dataset.state = connectionVisualState();
  if (collectorDetail) collectorDetail.textContent = detail;
  collectorCard.setAttribute("aria-label", `${title}. ${detail}`);
}

function markUpdated(timestamp = new Date().toISOString()) {
  state.lastUpdatedAt = timestamp;
  renderConnectionIndicator();
  refreshKpiTicker();
}

function setSocketState(nextState) {
  state.socketState = nextState;
  renderConnectionIndicator();
  refreshKpiTicker();
}

function clearSocketReconnectTimer() {
  if (socketReconnectTimerId == null) {
    return;
  }
  window.clearTimeout(socketReconnectTimerId);
  socketReconnectTimerId = null;
}

function nextOverloadReconnectDelayMs() {
  const exponent = Math.min(socketReconnectAttempts, 4);
  const baseDelay = Math.min(
    SOCKET_BACKOFF_MAX_DELAY_MS,
    SOCKET_BACKOFF_BASE_DELAY_MS * (2 ** exponent),
  );
  const jitter = Math.round(baseDelay * (Math.random() * 0.4));
  return Math.min(SOCKET_BACKOFF_MAX_DELAY_MS, baseDelay + jitter);
}

function scheduleSocketReconnect(delayMs) {
  clearSocketReconnectTimer();
  socketReconnectTimerId = window.setTimeout(() => {
    socketReconnectTimerId = null;
    connectEvents();
  }, delayMs);
}

function setCollectorStatus(data) {
  state.collectorStatus = data || null;
  renderConnectionIndicator();
  refreshKpiTicker();
}

function setPerspective(data) {
  state.perspective = data;
  renderPerspectiveLabel();
  renderChannelScopedUi();

  if (state.nodes.length) {
    renderNodesView();
  }
}

function portCategory(portnum) {
  const normalized = String(portnum || "");
  if (normalized === "TEXT_MESSAGE_APP") {
    return "text";
  }
  if (normalized.includes("POSITION")) {
    return "position";
  }
  if (
    normalized.includes("TELEMETRY")
    || normalized.includes("NODEINFO")
    || normalized.includes("NEIGHBORINFO")
    || normalized.includes("PAXCOUNTER")
    || normalized.includes("AIRQUALITY")
    || normalized.includes("STORE_FORWARD")
    || normalized.includes("RANGE_TEST")
  ) {
    return "telemetry";
  }
  if (
    normalized.includes("ADMIN")
    || normalized.includes("ROUTING")
    || normalized.includes("TRACEROUTE")
    || normalized.includes("REMOTE_HARDWARE")
    || normalized.includes("SIMULATOR")
  ) {
    return "admin";
  }
  return "other";
}

function portBadgeText(portnum) {
  const category = portCategory(portnum);
  if (category === "text") {
    return t("traffic.port.text");
  }
  if (category === "position") {
    return t("traffic.port.positionShort");
  }
  if (category === "telemetry") {
    return t("traffic.port.telemetryShort");
  }
  if (category === "admin") {
    return t("traffic.port.admin");
  }
  return t("traffic.port.other");
}

function packetCountsForRecentActivity(packet) {
  return portCategory(packet?.portnum) !== "admin";
}

function packetFilterMatches(packet) {
  const category = portCategory(packet.portnum);
  if (category === "admin") {
    return false;
  }
  return state.packetFilter === "all" || category === state.packetFilter;
}

function nodeMatchesQuery(node) {
  if (!state.nodeQuery.trim()) {
    return true;
  }
  const haystack = [
    nodeLabel(node),
    nodeSecondaryLabel(node),
    node?.node_id,
    node?.short_name,
    node?.long_name,
    node?.node_num,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(state.nodeQuery.trim().toLowerCase());
}

function nodeMatchesActiveFilter(node) {
  if (!state.nodeFilters.size) {
    return true;
  }
  return [...state.nodeFilters].every((filterKey) => {
    if (filterKey === "active") {
      return nodeIsActive(node);
    }
    if (filterKey === "direct-rf") {
      return nodeIsDirectRf(node);
    }
    if (filterKey === "mapped") {
      return nodeHasCoordinates(node);
    }
    if (filterKey === "mqtt") {
      return nodeIsMqtt(node);
    }
    if (filterKey === "stale") {
      return nodeIsStale(node);
    }
    return true;
  });
}

function visibleNodeItems() {
  return rankRosterNodes(
    state.nodes.filter((node) => (
      node.node_num === state.selectedNodeNum
      || (nodeMatchesQuery(node) && nodeMatchesActiveFilter(node))
    )),
  );
}

function recentActivityPackets() {
  return Array.isArray(state.recentActivityPackets) ? state.recentActivityPackets : [];
}

function nodeActivityCount(nodeOrNum) {
  const node = typeof nodeOrNum === "object" && nodeOrNum !== null
    ? nodeOrNum
    : nodeByNum(nodeOrNum);
  const nodeNum = typeof nodeOrNum === "object" && nodeOrNum !== null
    ? nodeOrNum.node_num
    : nodeOrNum;
  if (nodeNum == null) {
    return 0;
  }
  if (node && Number.isFinite(Number(node.activity_count_60m))) {
    return intValue(node.activity_count_60m);
  }
  return recentActivityPackets().filter((packet) => packet?.from_node_num === nodeNum).length;
}

function nodeIsWindowActive(node, nowMs = Date.now()) {
  if (!node) {
    return false;
  }
  if (nodeIsActive(node, nowMs)) {
    return true;
  }
  return nodeActivityCount(node) > 0;
}

function nodeType(node) {
  const hardware = String(node?.hardware_model || "").toUpperCase();
  const role = String(node?.role || "").toUpperCase();
  if (node?.via_mqtt || hardware.includes("GATEWAY") || hardware.includes("MQTT")) {
    return "gateway";
  }
  if (role === "ROUTER") {
    return "router";
  }
  if (hardware.includes("TRACKER") || hardware.includes("T1000")) {
    return "mobile";
  }
  return "client";
}

function computeRouteDegreeMap(routes) {
  const degreeMap = new Map();
  for (const route of routes) {
    for (const nodeNum of route.path_node_nums) {
      degreeMap.set(nodeNum, (degreeMap.get(nodeNum) || 0) + 1);
    }
  }
  return degreeMap;
}

function nodeSignificance(node, degreeMap) {
  let score = 0;
  const type = nodeType(node);
  if (type === "gateway") score += 3;
  else if (type === "router") score += 2;
  else if (type === "mobile") score += 0.5;
  score += clamp(nodeActivityCount(node) / 3, 0, 4);
  const degree = degreeMap.get(node.node_num) || 0;
  score += clamp(degree / 4, 0, 3);
  if (isDirectNode(node)) score += 1;
  return clamp(score / 11, 0, 1);
}

function isImportantNode(node) {
  if (node.node_num === state.selectedNodeNum) return true;
  const type = nodeType(node);
  if (type === "gateway" || type === "router") return true;
  if (nodeActivityCount(node) >= 4) return true;
  return false;
}

function selectedNeighborhood(routes) {
  if (state.selectedNodeNum == null) {
    return null;
  }
  const neighborSet = new Set();
  neighborSet.add(state.selectedNodeNum);
  for (const route of routes) {
    if (routeSelected(route)) {
      for (const nodeNum of route.path_node_nums) {
        neighborSet.add(nodeNum);
      }
    }
  }
  return neighborSet;
}

function renderMapNotes() {
  if (!state.showRoutes) {
    mapNote.hidden = false;
    mapNote.textContent = t("map.routesHidden");
    return;
  }
  if (!activeMeshRoutes().length) {
    mapNote.hidden = false;
    mapNote.textContent = t("map.noRouteOverlays");
    return;
  }
  mapNote.hidden = true;
  mapNote.textContent = "";
}


function updateOverviewStats() {
  const nodeTotal = state.nodes.length;
  const activeCount = state.nodes.filter((n) => nodeIsActive(n)).length;

  if (nodesPanelCount) {
    nodesPanelCount.textContent = t("nodes.panelCount", {
      heard: formatWholeNumber(nodeTotal),
      active: formatWholeNumber(activeCount),
    });
  }
  renderMapHud();
}

function nodeRecentPacketMarkup(packet) {
  const category = portCategory(packet?.portnum);
  const pathTone = packet?.path_tone || packetPathTone(packet);
  const pathLabel = packet?.path_label || packetPathLabel(packet);
  const destinationLabel = packet?.destination_label || toNodeLabel(packet);
  const textPreview = typeof packet?.text_preview === "string" ? packet.text_preview.trim() : "";
  const snrLabel = formatNumber(packet?.rx_snr, 1, " dB");
  return `
    <article class="node-packet-card ${pathTone}">
      <div class="node-packet-meta">
        <span class="mono-text">${escapeHtml(formatTime(packet?.received_at))}</span>
        <span class="path-badge ${pathTone}">${escapeHtml(pathLabel)}</span>
      </div>
      <div class="node-packet-tags">
        <span class="port-badge ${category}">${escapeHtml(portBadgeText(packet?.portnum))}</span>
        <div class="node-packet-tag-group">
          <span class="node-packet-port mono-text">${escapeHtml(packet?.portnum || t("common.unknown"))}</span>
          <span class="node-packet-snr mono-text">${escapeHtml(`${t("traffic.snr")} ${snrLabel}`)}</span>
        </div>
      </div>
      <p class="node-packet-destination">${escapeHtml(t("nodes.toDestination", { destination: destinationLabel }))}</p>
      ${textPreview ? `<p class="node-packet-text">${escapeHtml(textPreview)}</p>` : ""}
    </article>
  `;
}

function renderNodeRecentPackets(node, detailPayload) {
  const isLoading = state.nodeDetailLoadingNodeNum === node.node_num && !detailPayload;
  const hasError = state.nodeDetailErrorNodeNum === node.node_num && !detailPayload;
  const recentPackets = Array.isArray(detailPayload?.recent_packets) ? detailPayload.recent_packets : [];

  let bodyMarkup;
  if (hasError) {
    bodyMarkup = `
      <div class="node-packets-empty">
        <p>${escapeHtml(t("nodes.recentPacketsUnavailable"))}</p>
      </div>
    `;
  } else if (isLoading) {
    bodyMarkup = `
      <div class="node-packets-empty">
        <p>${escapeHtml(t("nodes.loadingRecentPackets"))}</p>
      </div>
    `;
  } else if (!recentPackets.length) {
    bodyMarkup = `
      <div class="node-packets-empty">
        <p>${escapeHtml(t("nodes.noRecentPackets"))}</p>
      </div>
    `;
  } else {
    bodyMarkup = `
      <div class="node-packets-list">
        ${recentPackets.map(nodeRecentPacketMarkup).join("")}
      </div>
    `;
  }

  return `
    <section class="node-hud-section">
      <div class="node-hud-section-head">
        <h4>${escapeHtml(t("nodes.recentPackets"))}</h4>
      </div>
      ${bodyMarkup}
    </section>
  `;
}

function tracerouteAttemptStatusLabel(status) {
  if (typeof status !== "string" || !status.trim()) {
    return t("common.unknown");
  }
  const normalized = status.trim().toLowerCase();
  if (normalized === "success") return t("traceroute.success");
  if (normalized === "ack_only") return t("traceroute.ackOnly");
  if (normalized === "timeout") return t("traceroute.timeout");
  if (normalized === "error") return t("traceroute.error");
  return normalized.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function tracerouteAttemptTone(attempt) {
  const status = String(attempt?.status || "").toLowerCase();
  if (status === "success") {
    return "success";
  }
  if (status === "ack_only") {
    return "partial";
  }
  return "failed";
}

function tracerouteRouteLabel(route) {
  const pathNodeNums = Array.isArray(route?.path_node_nums) ? route.path_node_nums : [];
  if (!pathNodeNums.length) {
    return t("routes.unavailable");
  }
  return pathNodeNums.map((nodeNum) => {
    const node = nodeByNum(nodeNum);
    return nodeLabel(node || { node_num: nodeNum });
  }).join(" → ");
}

function tracerouteResultLabel(attempt) {
  return tracerouteAttemptStatusLabel(attempt?.status).toUpperCase().replaceAll(" ", "_");
}

function traceroutePathNodes(pathNodeNums) {
  return (Array.isArray(pathNodeNums) ? pathNodeNums : []).map((nodeNum) => {
    const node = nodeByNum(nodeNum);
    return {
      nodeNum,
      label: nodeLabel(node || { node_num: nodeNum }),
      isSelected: Number(nodeNum) === Number(state.selectedNodeNum),
    };
  });
}

function traceroutePathMarkup(pathNodeNums) {
  const nodes = traceroutePathNodes(pathNodeNums);
  if (!nodes.length) {
    return `<p class="traceroute-empty">${escapeHtml(t("routes.unavailable"))}</p>`;
  }
  return `
    <div class="traceroute-path">
      ${nodes.map((node, index) => `
        <span class="traceroute-path-node${node.isSelected ? " selected" : ""}">${escapeHtml(node.label)}</span>
        ${index < nodes.length - 1 ? '<span class="traceroute-path-arrow" aria-hidden="true">→</span>' : ""}
      `).join("")}
    </div>
  `;
}

function tracerouteMetaPill(label, value, tone = "") {
  return `
    <span class="traceroute-meta-pill${tone ? ` ${tone}` : ""}">
      <span class="traceroute-meta-pill-label">${escapeHtml(label)}</span>
      <span class="traceroute-meta-pill-value">${escapeHtml(value)}</span>
    </span>
  `;
}

function renderNodeTracerouteSection(detailPayload) {
  const lastAttempt = detailPayload?.last_traceroute_attempt || null;
  const lastSuccessful = detailPayload?.last_successful_traceroute_attempt || null;
  const latestComplete = detailPayload?.latest_complete_traceroute || null;
  if (!lastAttempt && !lastSuccessful && !latestComplete) {
    return `
      <section class="node-hud-section">
        <div class="node-hud-section-head">
          <h4>${escapeHtml(t("traceroute.title"))}</h4>
        </div>
        <div class="node-packets-empty">
          <p>${escapeHtml(t("traceroute.noAttempts"))}</p>
        </div>
      </section>
    `;
  }

  const latestCompleteRequestMeshId = latestComplete?.request_mesh_packet_id != null
    ? Number(latestComplete.request_mesh_packet_id)
    : null;
  const latestAttemptRequestId = lastAttempt?.request_mesh_packet_id != null ? Number(lastAttempt.request_mesh_packet_id) : null;
  const showLastAttempt = lastAttempt && (
    latestComplete == null
    || latestAttemptRequestId == null
    || latestCompleteRequestMeshId == null
    || latestAttemptRequestId !== latestCompleteRequestMeshId
    || String(lastAttempt.status || "").toLowerCase() !== "success"
  );

  const primaryTone = latestComplete ? "success" : (lastAttempt ? tracerouteAttemptTone(lastAttempt) : "failed");
  const primaryStatusLabel = latestComplete
    ? t("traceroute.completePath")
    : tracerouteAttemptStatusLabel(lastAttempt?.status);
  const completeSeenAt = latestComplete?.received_at || lastSuccessful?.requested_at || lastAttempt?.requested_at || null;
  const completeFullPath = Array.isArray(latestComplete?.full_path_node_nums)
    ? latestComplete.full_path_node_nums
    : [];
  const completeForwardPath = Array.isArray(latestComplete?.forward_path_node_nums)
    ? latestComplete.forward_path_node_nums
    : [];
  const completeReturnPath = Array.isArray(latestComplete?.return_path_node_nums)
    ? latestComplete.return_path_node_nums
    : [];
  const routeMarkup = latestComplete
    ? traceroutePathMarkup(completeFullPath)
    : traceroutePathMarkup((lastSuccessful?.route?.path_node_nums || lastAttempt?.route?.path_node_nums || []));
  const metaPills = [];
  if (completeSeenAt) {
    metaPills.push(tracerouteMetaPill(t("traceroute.seen"), formatTime(completeSeenAt)));
  }
  if (latestComplete?.hop_count != null) {
    metaPills.push(tracerouteMetaPill(t("traceroute.hops"), String(latestComplete.hop_count)));
  }
  if (latestComplete?.request_mesh_packet_id != null) {
    metaPills.push(tracerouteMetaPill(t("traceroute.request"), `#${latestComplete.request_mesh_packet_id}`));
  } else if (lastSuccessful?.request_mesh_packet_id != null) {
    metaPills.push(tracerouteMetaPill(t("traceroute.request"), `#${lastSuccessful.request_mesh_packet_id}`));
  } else if (lastAttempt?.request_mesh_packet_id != null) {
    metaPills.push(tracerouteMetaPill(t("traceroute.request"), `#${lastAttempt.request_mesh_packet_id}`));
  }
  if (latestComplete?.discovery_request_id != null) {
    metaPills.push(tracerouteMetaPill(t("traceroute.trace"), `#${latestComplete.discovery_request_id}`));
  }
  if (completeForwardPath.length && completeReturnPath.length) {
    metaPills.push(tracerouteMetaPill(t("path.pattern"), t("path.roundTrip"), "success"));
  } else if (completeForwardPath.length) {
    metaPills.push(tracerouteMetaPill(t("path.pattern"), t("path.forwardOnly"), "partial"));
  }
  const debugSummary = showLastAttempt
    ? `${formatTime(lastAttempt.requested_at)} · ${tracerouteResultLabel(lastAttempt)}`
    : null;
  const routeTitle = latestComplete ? t("routes.latestRoute") : primaryStatusLabel;

  return `
    <section class="node-hud-section">
      <div class="node-hud-section-head">
        <h4>${escapeHtml(t("traceroute.title"))}</h4>
      </div>
      <article class="traceroute-summary-card ${primaryTone}">
        <div class="traceroute-summary-head">
          <div>
            <h5>${escapeHtml(routeTitle)}</h5>
          </div>
          <span class="traceroute-inline-status ${primaryTone}">${escapeHtml(latestComplete ? t("common.complete") : tracerouteResultLabel(lastAttempt))}</span>
        </div>

        ${metaPills.length ? `
          <div class="traceroute-meta-row">
            ${metaPills.join("")}
          </div>
        ` : ""}

        <div class="traceroute-route-card">
          <div class="traceroute-route-head">
            <span class="traceroute-route-label">${escapeHtml(t("routes.route"))}</span>
            ${completeSeenAt ? `<span class="traceroute-route-age mono-text">${escapeHtml(formatRelativeTime(completeSeenAt))}</span>` : ""}
          </div>
          ${routeMarkup}
        </div>

        ${debugSummary || (showLastAttempt && lastAttempt?.detail) ? `
          <div class="traceroute-debug-row ${tracerouteAttemptTone(lastAttempt)}">
            ${debugSummary ? `<span class="traceroute-debug-value strong">${escapeHtml(debugSummary)}</span>` : ""}
            ${lastAttempt?.detail ? `<span class="traceroute-debug-value">${escapeHtml(lastAttempt.detail)}</span>` : ""}
          </div>
        ` : ""}
      </article>
    </section>
  `;
}

function renderNodeDetail(node) {
  if (!node) {
    nodeDetail.innerHTML = `
      <div class="hud-empty">
        <h3>${escapeHtml(t("nodes.noNodeSelectedTitle"))}</h3>
        <p>${escapeHtml(t("nodes.noNodeSelectedBody"))}</p>
      </div>
    `;
    return;
  }

  const detailPayload = state.nodeDetails.get(node.node_num);
  const detailNode = detailPayload?.node ? { ...node, ...detailPayload.node } : node;
  const insights = detailPayload?.insights || null;
  const recentPackets = Array.isArray(detailPayload?.recent_packets) ? detailPayload.recent_packets : [];
  const metricHistory = Array.isArray(detailPayload?.metric_history) ? detailPayload.metric_history : [];
  const freshness = nodeFreshness(detailNode);
  const hudTone = freshness;
  const pathLabel = nodePathLabel(detailNode, detailPayload);
  const roleLabel = [detailNode.role, detailNode.hardware_model].filter(Boolean).join(" / ") || t("common.node");

  nodeDetail.innerHTML = `
    <div class="node-hud-card ${hudTone}">
      <div class="node-hud-head">
        <div>
          <h3>${escapeHtml(nodeLabel(detailNode))}</h3>
          <p class="node-hud-subtitle">${escapeHtml(`${roleLabel} · ${nodePathDescription(detailNode, detailPayload)}`)}</p>
        </div>
        <div class="node-hud-state ${hudTone}">${escapeHtml(freshnessLabel(detailNode))}</div>
      </div>

      <div class="node-hud-metrics">
        ${metric(t("nodes.metric.path"), pathLabel)}
        ${metric(t("nodes.metric.lastHeard"), formatTime(detailNode.last_heard_at), "", detailNode.first_heard_at ? t("nodes.metric.first", { time: formatTime(detailNode.first_heard_at) }) : "")}
        ${metric(t("nodes.metric.packetsHeard"), formatWholeNumber(insights?.heard_packets))}
        ${metric(t("nodes.metric.battery"), detailNode.battery_level == null ? t("common.na") : `${Math.round(detailNode.battery_level)}%`)}
        ${nodeSnrCard(detailNode, insights, recentPackets, freshness)}
        ${nodeUtilizationCard(detailNode, metricHistory, freshness)}
        ${nodePacketBreakdownCard(insights)}
      </div>

      ${renderNodeTracerouteSection(detailPayload)}
      ${renderNodeRecentPackets(detailNode, detailPayload)}
    </div>
  `;
}

function nodeProximityTone(node) {
  const status = nodeStatus(node);
  if (status === "mqtt") return "mqtt";
  if (status === "direct" || isLocalNode(node)) return "direct";
  const hops = Number(node.hops_away);
  if (hops <= 1) return "direct";
  if (hops === 2) return "relayed";
  return "relayed";
}

function renderNodeList() {
  const items = visibleNodeItems();
  if (!items.length) {
    const hasFilters = state.nodeFilters.size > 0 || Boolean(state.nodeQuery.trim());
    const emptyBody = hasFilters
      ? t("nodes.noMatchingBody")
      : channelScopedText("nodes.noNodesBody", "nodes.noNodesBodyWithChannel");
    nodeList.innerHTML = `
      <div class="node-list-empty">
        <h3>${escapeHtml(hasFilters ? t("nodes.noMatchingTitle") : t("nodes.noNodesTitle"))}</h3>
        <p>${escapeHtml(emptyBody)}</p>
      </div>
    `;
    return;
  }

  const nowMs = Date.now();
  nodeList.innerHTML = `
    <div class="node-list-body">
      ${items.map((node) => {
        const status = nodeStatus(node);
        const proxTone = nodeProximityTone(node);
        const selectedClass = node.node_num === state.selectedNodeNum ? " selected" : "";
        const isDirect = proxTone === "direct";
        const hopPill = isDirect
          ? ""
          : (status === "mqtt"
            ? `<span class="node-row-hop">MQTT</span>`
            : `<span class="node-row-hop">${escapeHtml(t("path.relayed"))}</span>`);
        const nodeId = node.node_id ? `!${escapeHtml(node.node_id)}` : (node.node_num ? `#${node.node_num}` : "");
        return `
          <button
            type="button"
            class="node-row${selectedClass}"
            data-node-num="${node.node_num}"
          >
            <span class="node-row-dot ${proxTone}"></span>
            <span class="node-row-left">
              <span class="node-row-main">${escapeHtml(nodeLabel(node))}</span>
              <span class="node-row-id">${nodeId}</span>
            </span>
            <span class="node-row-right">
              ${hopPill}
              <span class="node-row-time">${escapeHtml(formatRelativeTime(node.last_heard_at, nowMs))}</span>
            </span>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function ensureMap() {
  if (mapState.map) {
    return mapState.map;
  }

  const map = L.map(mapRoot, {
    preferCanvas: true,
    zoomControl: false,
  });

  L.control.zoom({ position: "bottomright" }).addTo(map);

  const routePane = map.createPane("mesh-routes");
  routePane.style.zIndex = "340";
  routePane.style.pointerEvents = "none";
  const routeArrowPane = map.createPane("mesh-route-arrows");
  routeArrowPane.style.zIndex = "345";
  routeArrowPane.style.pointerEvents = "none";

  mapState.routeLayer = L.layerGroup().addTo(map);
  mapState.routeArrowLayer = L.layerGroup().addTo(map);
  mapState.markerLayer = L.layerGroup();
  mapState.markerLayer.addTo(map);
  mapState.map = map;
  applyBasemapTheme();
  if (!mapState.zoomListenerBound) {
    map.on("zoomend", () => {
      if (state.nodes.length) {
        renderMap(state.nodes);
      } else {
        renderMapNotes();
      }
    });
    mapState.zoomListenerBound = true;
  }
  map.setView([-34.6037, -58.3816], 11);
  window.setTimeout(() => map.invalidateSize(), 0);
  window.addEventListener("resize", () => map.invalidateSize(), { passive: true });
  return map;
}

function markerStyle(node, ctx) {
  const overlay = currentThemeOverlay();
  const markerPalette = overlay.markerPalette || THEME_REGISTRY[DEFAULT_UI_THEME].overlay.markerPalette;
  const nowMs = ctx.nowMs;
  const neighborhood = ctx.neighborhood;
  const degreeMap = ctx.degreeMap;
  const isSelected = node.node_num === state.selectedNodeNum;
  const active = nodeIsWindowActive(node, nowMs);
  const status = nodeStatus(node);
  const palette = markerPalette[status] || markerPalette.relayed;
  const significance = degreeMap ? nodeSignificance(node, degreeMap) : clamp(nodeActivityCount(node) / 6, 0, 1);
  const size = Math.round(
    interpolate(14, 32, significance)
    + (active ? 2 : 0)
    + (isSelected ? 4 : 0)
  );
  const baseOpacity = clamp(nodeSignalOpacity(node, nowMs) + (active ? 0.08 : 0), NODE_MIN_OPACITY, 0.98);
  const dimmed = neighborhood != null && !neighborhood.has(node.node_num);
  const opacity = dimmed ? clamp(baseOpacity * 0.25, 0.06, 0.20) : baseOpacity;
  const borderColor = isSelected ? markerPalette.selected.borderColor : palette.borderColor;
  const haloColor = isSelected ? markerPalette.selected.haloColor : palette.haloColor;
  return {
    size,
    opacity,
    shape: overlay.markerShape,
    fillColor: palette.fillColor,
    glyphColor: palette.glyphColor,
    borderColor,
    borderWidth: isSelected ? 3.1 : (status === "direct" ? 2.2 : 1.8),
    haloColor,
    haloOpacity: dimmed ? 0.15 : (isSelected || active ? 1 : 0.7),
    fillOpacity: dimmed ? 0.3 : (active ? 0.9 : 0.78),
  };
}

function nodeGlyphMarkup(_type, _color) {
  return "";
}

function markerIcon(node, ctx) {
  const overlay = currentThemeOverlay();
  const style = markerStyle(node, ctx);
  const size = style.size;
  const zoom = ctx.zoom;
  const neighborhood = ctx.neighborhood;
  const inNeighborhood = neighborhood != null && neighborhood.has(node.node_num);

  let showLabel;
  if (zoom <= 10) {
    showLabel = false;
  } else if (zoom <= 13) {
    showLabel = (isImportantNode(node) || inNeighborhood) && !!node.short_name;
  } else {
    showLabel = size >= 16 && !!node.short_name;
  }

  const labelHeight = showLabel ? 12 : 0;
  const labelHtml = showLabel
    ? `<span class="node-marker-label" style="color:${overlay.markerLabelColor}">${escapeHtml(node.short_name)}</span>`
    : "";
  const iconSize = style.shape === "pin"
    ? [size, size + Math.round(size * 0.6) + labelHeight]
    : [size, size + labelHeight];
  const iconAnchor = style.shape === "pin"
    ? [size / 2, size + Math.round(size * 0.28)]
    : [size / 2, size / 2];
  const tooltipAnchor = style.shape === "pin"
    ? [0, -(size * 0.7)]
    : [0, -(size / 2)];
  const svgMarkup = style.shape === "pin"
    ? `
        <svg width="${size}" height="${size + Math.round(size * 0.6)}" viewBox="0 0 40 56" aria-hidden="true">
          <defs>
            <filter id="pin-shadow-${node.node_num}" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="rgba(22,35,43,0.18)"/>
            </filter>
          </defs>
          <path d="M20 54C20 54 35 34.4 35 21C35 12.7 28.3 6 20 6S5 12.7 5 21c0 13.4 15 33 15 33Z"
            fill="${style.fillColor}" fill-opacity="${style.fillOpacity}"
            stroke="${style.borderColor}" stroke-width="${style.borderWidth}"
            filter="url(#pin-shadow-${node.node_num})"></path>
          <circle cx="20" cy="21" r="6.5" fill="${style.glyphColor}" fill-opacity="0.94"></circle>
        </svg>
      `
    : `
        <svg width="${size}" height="${size}" viewBox="0 0 36 36" aria-hidden="true">
          <defs>
            <radialGradient id="halo-${node.node_num}">
              <stop offset="0%" stop-color="${style.haloColor}" stop-opacity="${style.haloOpacity}"/>
              <stop offset="70%" stop-color="${style.haloColor}" stop-opacity="${(style.haloOpacity * 0.3).toFixed(2)}"/>
              <stop offset="100%" stop-color="${style.haloColor}" stop-opacity="0"/>
            </radialGradient>
          </defs>
          <circle cx="18" cy="18" r="17" fill="url(#halo-${node.node_num})"></circle>
          <circle cx="18" cy="18" r="12.5" fill="${style.fillColor}" fill-opacity="${style.fillOpacity}"></circle>
        </svg>
      `;
  return L.divIcon({
    className: "",
    html: `
      <div class="node-marker-shell" style="width:${size}px;opacity:${style.opacity.toFixed(3)};">
        ${svgMarkup}
        ${labelHtml}
      </div>
    `,
    iconSize,
    iconAnchor,
    tooltipAnchor,
  });
}

function popupMarkup(node) {
  const roleHardware = [node.role, node.hardware_model].filter(Boolean).join(" / ") || t("common.nodeTelemetry");
  return `
    <div class="mesh-node-tooltip-card">
      <div class="mesh-node-tooltip-title">${escapeHtml(nodeLabel(node))}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(roleHardware)}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(nodePathDescription(node))}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(t("map.lastHeard", { time: formatTime(node.last_heard_at) }))}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(`${t("traffic.snr")} ${formatNumber(node.last_snr, 1, " dB")}`)}</div>
    </div>
  `;
}

function fitMapToFocus() {
  const mappedNodes = sortNodes(state.nodes).filter((node) => nodeHasCoordinates(node) && nodeIsVisible(node));
  if (!mappedNodes.length) {
    return;
  }

  const map = ensureMap();
  const focus = focusNodes(mappedNodes);
  const points = focus.map((node) => [node.latitude, node.longitude]);
  if (points.length === 1) {
    map.setView(points[0], 13);
  } else {
    map.fitBounds(L.latLngBounds(points).pad(0.18), { maxZoom: 13 });
  }
  mapState.initialViewApplied = true;
}

function centerMapOnNode(node) {
  if (!nodeHasCoordinates(node)) {
    return;
  }
  const map = ensureMap();
  const zoom = Math.max(map.getZoom(), 13);
  map.flyTo([node.latitude, node.longitude], Math.min(zoom, 15), { duration: 0.6 });
}

function syncMapSize() {
  if (!mapState.map) {
    return;
  }
  window.requestAnimationFrame(() => mapState.map.invalidateSize());
}

function renderRailView() {
  const expanded = state.nodesDrawerOpen;
  const chatVisible = expanded && state.activeDrawerView === "chat";
  if (nodeRail) {
    nodeRail.dataset.state = expanded ? "expanded" : "collapsed";
  }
  if (nodesPanel) {
    nodesPanel.hidden = state.activeDrawerView !== "nodes" || !expanded;
  }
  if (intelPanel) {
    intelPanel.hidden = state.activeDrawerView !== "signals" || !expanded;
  }
  if (chatPanel) {
    const wasHidden = chatPanel.hidden;
    chatPanel.hidden = !chatVisible;
    if (wasHidden && chatVisible) {
      scheduleChatScrollToBottom("auto");
    }
  }
  if (optionsPanel) {
    optionsPanel.hidden = state.activeDrawerView !== "options" || !expanded;
  }
  if (mapViewport) {
    mapViewport.classList.toggle("rail-expanded", expanded);
  }
  if (railToggleNodes) {
    railToggleNodes.classList.toggle("active", expanded && state.activeDrawerView === "nodes");
    railToggleNodes.setAttribute("aria-expanded", String(expanded && state.activeDrawerView === "nodes"));
  }
  if (railToggleChat) {
    railToggleChat.classList.toggle("active", expanded && state.activeDrawerView === "chat");
    railToggleChat.setAttribute("aria-expanded", String(expanded && state.activeDrawerView === "chat"));
  }
  if (railToggleSignals) {
    railToggleSignals.classList.toggle("active", expanded && state.activeDrawerView === "signals");
    railToggleSignals.setAttribute("aria-expanded", String(expanded && state.activeDrawerView === "signals"));
  }
  if (railToggleOptions) {
    railToggleOptions.classList.toggle("active", expanded && state.activeDrawerView === "options");
    railToggleOptions.setAttribute("aria-expanded", String(expanded && state.activeDrawerView === "options"));
  }
  if (chatVisible && chatPendingScrollBehavior) {
    scheduleChatScrollToBottom(chatPendingScrollBehavior);
  }
}

function setDrawerView(nextView) {
  state.activeDrawerView = nextView === "signals" || nextView === "chat" || nextView === "options"
    ? nextView
    : "nodes";
  renderRailView();
  syncMapSize();
}

function setNodeRailOpen(open) {
  state.nodesDrawerOpen = open;
  renderRailView();
  syncMapSize();
}

function setTrafficDrawerOpen(open) {
  state.trafficDrawerOpen = open;
  if (trafficPanel) {
    trafficPanel.setAttribute("aria-hidden", open ? "false" : "true");
  }
  if (railToggleTraffic) {
    railToggleTraffic.classList.toggle("active", open);
    railToggleTraffic.setAttribute("aria-expanded", String(open));
  }
  if (mapViewport) {
    mapViewport.classList.toggle("traffic-open", open);
  }
  syncMapSize();
}

function setInspectorOpen(open) {
  if (inspectorPanel) {
    inspectorPanel.classList.toggle("is-open", open);
  }
  if (mapViewport) {
    mapViewport.classList.toggle("inspector-open", open);
  }
  syncMapSize();
}

function clearSelectedNode() {
  if (state.selectedNodeNum == null) {
    return false;
  }
  state.selectedNodeNum = null;
  renderNodesView();
  return true;
}

function dismissTopmostLayer() {
  if (clearSelectedNode()) {
    return true;
  }
  if (state.trafficDrawerOpen) {
    setTrafficDrawerOpen(false);
    return true;
  }
  if (state.nodesDrawerOpen) {
    setNodeRailOpen(false);
    return true;
  }
  return false;
}

function activeElementIsEditable() {
  const activeElement = document.activeElement;
  return activeElement instanceof Element
    && Boolean(activeElement.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])"));
}

function renderMapHud() {}

function renderRouteToggle() {
  if (!routeToggle) {
    return;
  }
  routeToggle.textContent = state.showRoutes ? t("routes.hide") : t("routes.show");
  routeToggle.setAttribute('aria-pressed', String(state.showRoutes));
}

function renderMap(items) {
  const nowMs = Date.now();
  const mappedNodes = sortNodes(items).filter((node) => nodeHasCoordinates(node) && nodeIsVisible(node, nowMs));
  const map = ensureMap();
  const routes = activeMeshRoutes(nowMs);
  state.drawnRouteCount = routes.length;
  renderRouteToggle();
  renderMapNotes();

  if (!mappedNodes.length) {
    state.remoteNodeNums = new Set();
    mapEmpty.textContent = state.nodes.some(nodeHasCoordinates)
      ? t("map.noMappedNodes24h")
      : channelScopedText("map.waitingForNodeLocations", "map.waitingForNodeLocationsWithChannel");
    mapEmpty.hidden = false;
    mapNote.hidden = true;
    mapNote.textContent = "";
    if (mapState.routeLayer) {
      mapState.routeLayer.clearLayers();
      mapState.routeLinesByKey.clear();
    }
    if (mapState.routeArrowLayer) {
      mapState.routeArrowLayer.clearLayers();
    }
    if (mapState.markerLayer) {
      mapState.markerLayer.clearLayers();
      mapState.markersByNodeNum.clear();
    }
    refreshKpiTicker();
    updateOverviewStats();
    return;
  }

  const neighborhood = selectedNeighborhood(routes);
  const degreeMap = computeRouteDegreeMap(routes);
  const zoom = map.getZoom();
  const ctx = { nowMs, neighborhood, degreeMap, zoom };

  state.remoteNodeNums = new Set();
  mapEmpty.textContent = channelScopedText("map.waitingForNodeLocations", "map.waitingForNodeLocationsWithChannel");
  mapEmpty.hidden = true;
  mapState.routeLayer.clearLayers();
  mapState.routeArrowLayer.clearLayers();
  mapState.routeLinesByKey.clear();
  mapState.markerLayer.clearLayers();
  mapState.markersByNodeNum.clear();

  routes
    .map((route) => [route, routeLatLngs(route, nowMs)])
    .filter((entry) => entry[1] !== null)
    .forEach(([route, latLngs]) => {
      const style = routeStyle(route, ctx);
      const glowLine = L.polyline(
        latLngs,
        {
          color: style.color,
          weight: style.weight + 3,
          opacity: Math.min(style.opacity * 0.10, 0.08),
          lineCap: "round",
          lineJoin: "round",
          pane: "mesh-routes",
        },
      );
      glowLine.addTo(mapState.routeLayer);
      const line = L.polyline(
        latLngs,
        {
          ...style,
          pane: "mesh-routes",
        },
      );
      line.addTo(mapState.routeLayer);
      mapState.routeLinesByKey.set(routeKey(route), line);
      routeArrowMarkers(map, route, latLngs, style).forEach((arrowMarker) => {
        arrowMarker.addTo(mapState.routeArrowLayer);
      });
    });

  mappedNodes.forEach((node) => {
    const marker = L.marker([node.latitude, node.longitude], {
      icon: markerIcon(node, ctx),
      keyboard: false,
      zIndexOffset: node.node_num === state.selectedNodeNum ? 1200 : (nodeIsWindowActive(node, nowMs) ? 120 : 0),
    });
    marker.bindTooltip(popupMarkup(node), {
      className: "mesh-node-tooltip",
      direction: "top",
      offset: [0, -8],
      opacity: 1,
      sticky: true,
    });
    marker.on("click", () => {
      selectNode(node.node_num, { openTooltip: true });
    });
    mapState.markerLayer.addLayer(marker);
    mapState.markersByNodeNum.set(node.node_num, marker);
  });

  const selectedRoutes = routes
    .filter((route) => routeSelected(route))
    .map((route) => mapState.routeLinesByKey.get(routeKey(route)))
    .filter(Boolean);
  selectedRoutes.forEach((line) => line.bringToFront());

  if (!mapState.initialViewApplied) {
    fitMapToFocus();
  } else {
    map.invalidateSize();
  }

  refreshKpiTicker();
  updateOverviewStats();
}

function renderNodesView() {
  ensureSelectedNode();
  renderMap(state.nodes);
  renderNodeDetail(nodeByNum(state.selectedNodeNum));
  renderNodeList();
  setInspectorOpen(state.selectedNodeNum != null);
  syncMapSize();

  if (state.selectedNodeNum != null) {
    void loadNodeDetail(state.selectedNodeNum);
  }
}

function renderMeshSummary(data) {
  const previousSummary = state.meshSummary;
  state.meshSummary = data;
  state.meshSummaryPrevious = previousSummary;
  renderKpiTicker(data);
  const nodes = data?.nodes || {};
  const traffic = data?.traffic || {};
  const receiver = data?.receiver || null;
  const totalNodes = intValue(nodes.total);
  const mappedNodes = intValue(nodes.mapped);
  const totalPackets = intValue(traffic.packets);
  const directPackets = intValue(traffic.direct);
  const relayedPackets = intValue(traffic.relayed);
  const mqttPackets = intValue(traffic.mqtt);
  const textPackets = intValue(traffic.text);
  const positionPackets = intValue(traffic.position);
  const telemetryPackets = intValue(traffic.telemetry);
  const otherPackets = Math.max(0, totalPackets - textPackets - positionPackets - telemetryPackets);

  // Block 1 — Coverage: 2-column metric grid
  intelGrid.innerHTML = [
    heardNodesPanel(totalNodes, data),
    coveragePanel(mappedNodes, totalNodes, data),
  ].join("");

  if (!totalPackets && !totalNodes) {
    intelStory.innerHTML = `
      ${channelUtilizationBlock(receiver)}
      <div class="hud-empty compact">
        <p>${escapeHtml(t("signals.waitingIntel"))}</p>
      </div>
    `;
    updateOverviewStats();
    return;
  }

  // Block 2 — Routing health: proportional bars by signal path
  const routingTypes = [
    { label: t("path.directRf"), value: directPackets, tone: "direct" },
    { label: t("path.relayed"), value: relayedPackets, tone: "relayed" },
    { label: t("path.mqtt"), value: mqttPackets, tone: "mqtt" },
  ];
  const routingHealthHtml = `
    <div class="signals-section">
      <span class="signals-section-label">${escapeHtml(t("signals.routingHealth"))}</span>
      <div class="routing-health">
        <div class="packet-breakdown">
          ${routingTypes.map((type) => packetBreakdownRow(type, totalPackets)).join("")}
        </div>
        ${routingHealthRow(t("signals.totalPackets"), formatWholeNumber(totalPackets))}
      </div>
    </div>
  `;

  // Block 3 — Packet breakdown: proportional bars (share of total traffic)
  const breakdownTypes = [
    { label: t("signals.packetType.text"), value: textPackets, tone: "text" },
    { label: t("signals.packetType.telemetry"), value: telemetryPackets, tone: "telemetry" },
    { label: t("signals.packetType.position"), value: positionPackets, tone: "position" },
    { label: t("signals.packetType.other"), value: otherPackets, tone: "other" },
  ];

  const breakdownHtml = `
    <div class="signals-section">
      <span class="signals-section-label">${escapeHtml(t("signals.packetBreakdown"))}</span>
      <div class="packet-breakdown">
        ${breakdownTypes.map((t) => packetBreakdownRow(t, totalPackets)).join("")}
      </div>
    </div>
  `;

  // Block 4 — Channel utilization (compact, last)
  intelStory.innerHTML = [
    routingHealthHtml,
    breakdownHtml,
    channelUtilizationBlock(receiver),
  ].join("");
  updateOverviewStats();
}

function renderMeshRoutes(data) {
  state.meshRoutes = data || { routes: [], stats: { total: 0, forward: 0, return: 0 } };
  if (state.nodes.length) {
    renderMap(state.nodes);
    return;
  }
  state.drawnRouteCount = 0;
  refreshKpiTicker();
}

function packetRowMarkup(packet) {
  const category = portCategory(packet.portnum);
  const hops = packetHopsTaken(packet);
  const pathTone = packetPathTone(packet);
  const isMqtt = pathTone === "mqtt";
  const isUnknown = hops == null && !isMqtt && pathTone !== "local";
  const isHighHop = hops != null && hops >= 4;
  const pathCellClass = isHighHop ? " path-cell-high" : "";

  const fromName = fromNodeLabel(packet);
  const fromId = packet.from_node_num != null ? `#${packet.from_node_num}` : "";

  const pathContent = `<span class="path-badge ${pathTone}">${escapeHtml(isUnknown ? t("common.unknown") : packetPathLabel(packet))}</span>`;

  return `
    <tr class="packet-row ${category}">
      <td class="mono-text">${escapeHtml(formatTime(packet.received_at))}</td>
      <td>
        <div class="table-node">
          <span class="table-node-main">${escapeHtml(fromName)}</span>
          <span class="table-node-sub mono-text">${escapeHtml(fromId)}</span>
        </div>
      </td>
      <td>
        <div class="table-node">
          <span class="table-node-main">${escapeHtml(toNodeLabel(packet))}</span>
          <span class="table-node-sub mono-text">${escapeHtml(packet.to_node_num === BROADCAST_NODE_NUM ? t("common.broadcast").toLocaleUpperCase(currentIntlLocale()) : `#${packet.to_node_num ?? t("common.na")}`)}</span>
        </div>
      </td>
      <td>
        <div class="port-cell">
          <span class="port-badge ${category}">${escapeHtml(portBadgeText(packet.portnum))}</span>
        </div>
      </td>
      <td class="mono-text">${escapeHtml(formatNumber(packet.rx_snr, 1, " dB"))}</td>
      <td class="${pathCellClass}">
        <div class="port-cell">${pathContent}</div>
      </td>
    </tr>
  `;
}

function visiblePackets(items = state.packets) {
  return items.filter(packetFilterMatches);
}

function packetRequestLimit(limit) {
  return Math.min(PACKETS_API_MAX_LIMIT, limit + PACKETS_FETCH_STEP);
}

function packetStorageLimit(currentCount = state.packets.length) {
  return Math.min(PACKETS_API_MAX_LIMIT, Math.max(currentCount, packetRequestLimit(state.packetLimit)));
}

function needsPacketTopUp(items = state.packets, visibleLimit = state.packetLimit) {
  return visiblePackets(items).length < visibleLimit && items.length < PACKETS_API_MAX_LIMIT;
}

function queuePacketTopUp() {
  if (!needsPacketTopUp()) {
    return;
  }
  void loadPackets().catch(handleLoadError);
}

async function fetchPacketsForVisibleLimit(limit) {
  let requestLimit = packetRequestLimit(limit);
  let items = await fetchJson(`/api/packets?limit=${requestLimit}`);

  while (
    visiblePackets(items).length < limit
    && items.length === requestLimit
    && requestLimit < PACKETS_API_MAX_LIMIT
  ) {
    requestLimit = Math.min(PACKETS_API_MAX_LIMIT, requestLimit + PACKETS_FETCH_STEP);
    items = await fetchJson(`/api/packets?limit=${requestLimit}`);
  }

  return items;
}

function updatePacketExportButton(items = visiblePackets()) {
  if (!exportPacketsButton) {
    return;
  }
  const visibleCount = items.length;
  exportPacketsButton.disabled = visibleCount === 0;
  const actionLabel = visibleCount
    ? t("traffic.exportVisibleCountCsv", { count: formatWholeNumber(visibleCount) })
    : t("traffic.noVisiblePacketsToExport");
  exportPacketsButton.title = actionLabel;
  exportPacketsButton.setAttribute("aria-label", actionLabel);
}

function packetExportCsv(items) {
  const header = [
    "id",
    "received_at",
    "from_name",
    "from_node_num",
    "to_name",
    "to_node_num",
    "portnum",
    "port_label",
    "path_label",
    "path_tone",
  ];
  const rows = items.map((packet) => [
    packet?.id,
    packet?.received_at,
    fromNodeLabel(packet),
    packet?.from_node_num,
    toNodeLabel(packet),
    packet?.to_node_num,
    packet?.portnum,
    portBadgeText(packet?.portnum),
    packetPathLabel(packet),
    packetPathTone(packet),
  ]);
  return [
    header.map(csvEscape).join(","),
    ...rows.map((row) => row.map(csvEscape).join(",")),
  ].join("\n");
}

function exportVisiblePackets() {
  const items = visiblePackets();
  if (!items.length) {
    updatePacketExportButton(items);
    return;
  }
  const csv = packetExportCsv(items);
  const filterSuffix = state.packetFilter === "all" ? "all" : state.packetFilter;
  const link = document.createElement("a");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `meshseer-packets-${filterSuffix}-${fileTimestampPart()}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function updatePacketFilterButtons() {
  packetFilters.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === state.packetFilter);
  });
}

function updateNodeFilterButtons() {
  nodeFilters.querySelectorAll("[data-node-filter]").forEach((button) => {
    button.classList.toggle("active", state.nodeFilters.has(button.dataset.nodeFilter));
  });
}

function renderPackets(items) {
  const filteredItems = visiblePackets(items);
  updatePacketFilterButtons();
  updatePacketExportButton(filteredItems);

  if (!filteredItems.length) {
    packetsBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">${escapeHtml(t("traffic.noPacketsMatch"))}</td>
      </tr>
    `;
    updateOverviewStats();
    return;
  }

  packetsBody.innerHTML = filteredItems.map(packetRowMarkup).join("");
  updateOverviewStats();
}

function chatIsNearBottom() {
  if (!chatFeed) {
    return true;
  }
  return chatFeed.scrollHeight - chatFeed.scrollTop - chatFeed.clientHeight <= CHAT_STICKY_THRESHOLD_PX;
}

function chatMessageKey(item) {
  return item?.mesh_packet_id ?? item?.id ?? item?.received_at ?? null;
}

function resolvedChatScrollBehavior(behavior) {
  return behavior === "smooth" && !reducedMotionQuery?.matches ? "smooth" : "auto";
}

function scheduleChatScrollToBottom(behavior = "auto") {
  if (!chatFeed) {
    return;
  }

  const nextBehavior = resolvedChatScrollBehavior(behavior);
  if (chatPanel?.hidden || !state.nodesDrawerOpen || state.activeDrawerView !== "chat") {
    chatPendingScrollBehavior = nextBehavior;
    return;
  }

  window.requestAnimationFrame(() => {
    if (chatPanel?.hidden || !state.nodesDrawerOpen || state.activeDrawerView !== "chat") {
      chatPendingScrollBehavior = nextBehavior;
      return;
    }
    if (nextBehavior === "smooth" && !chatStickToBottom) {
      chatPendingScrollBehavior = null;
      return;
    }
    chatFeed.scrollTo({ top: chatFeed.scrollHeight, behavior: nextBehavior });
    chatStickToBottom = true;
    chatPendingScrollBehavior = null;
  });
}

function renderChat(items) {
  const shouldStick = chatStickToBottom;
  const latestMessageKey = chatMessageKey(items[0]);
  const hasNewLatestMessage = chatLastMessageKey != null && latestMessageKey != null && latestMessageKey !== chatLastMessageKey;

  if (!items.length) {
    const channelName = chatChannelName();
    const emptyBody = channelName
      ? t("chat.emptyBodyWithChannel", { channel: channelName })
      : t("chat.emptyBody");
    chatFeed.innerHTML = `
      <div class="chat-empty">
        <h3>${escapeHtml(t("chat.emptyTitle"))}</h3>
        <p>${escapeHtml(emptyBody)}</p>
      </div>
    `;
    chatLastMessageKey = null;
    updateOverviewStats();
    return;
  }

  const ordered = [...items].reverse();
  chatFeed.innerHTML = ordered.map((item) => {
    const sender = item.sender_label || fromNodeLabel(item);
    const pathTone = packetPathTone(item);
    return `
      <article class="chat-message ${pathTone}">
        <div class="chat-meta">
          <div class="chat-identity">
            <span class="chat-author">${escapeHtml(sender)}</span>
            <span class="path-badge ${pathTone}">${escapeHtml(packetPathLabel(item))}</span>
          </div>
          <span class="chat-time mono-text">${escapeHtml(formatTime(item.received_at))}</span>
        </div>
        <p class="chat-text">${escapeHtml(item.text_preview)}</p>
      </article>
    `;
  }).join("");

  if (shouldStick) {
    scheduleChatScrollToBottom(hasNewLatestMessage ? "smooth" : "auto");
  } else {
    chatPendingScrollBehavior = null;
  }
  chatLastMessageKey = latestMessageKey;
  updateOverviewStats();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(t("status.requestFailed", { status: response.status }));
  }
  return response.json();
}

async function loadNodeDetail(nodeNum, { force = false } = {}) {
  if (nodeNum == null || !nodeByNum(nodeNum)) {
    return;
  }
  if (!force && state.nodeDetails.has(nodeNum)) {
    return;
  }
  if (inflightNodeDetails.has(nodeNum)) {
    return;
  }

  inflightNodeDetails.add(nodeNum);
  state.nodeDetailLoadingNodeNum = nodeNum;
  state.nodeDetailErrorNodeNum = null;
  renderNodeDetail(nodeByNum(nodeNum));

  try {
    const payload = await fetchJson(`/api/nodes/${nodeNum}`);
    state.nodeDetails.set(nodeNum, payload);
  } catch (_error) {
    state.nodeDetailErrorNodeNum = nodeNum;
  } finally {
    inflightNodeDetails.delete(nodeNum);
    if (state.nodeDetailLoadingNodeNum === nodeNum) {
      state.nodeDetailLoadingNodeNum = null;
    }
    if (state.selectedNodeNum === nodeNum) {
      renderNodeDetail(nodeByNum(nodeNum));
    }
  }
}

async function loadHealth() {
  return runSingleFlight("health", async () => {
    const payload = await fetchJson("/api/status");
    state.uiDefaultTheme = normalizeThemeId(payload?.ui?.default_style) || DEFAULT_UI_THEME;
    applyThemeSelection(resolveStartupTheme(state.uiDefaultTheme));
    setCollectorStatus(payload.collector);
    setPerspective(payload.perspective);
    if (appVersionLabel && typeof payload.version === "string" && payload.version.trim()) {
      appVersionLabel.textContent = `v${payload.version}`;
    }
  });
}

async function loadNodes() {
  return runSingleFlight("nodes", async () => {
    state.nodes = (await fetchJson("/api/nodes/roster")).map((node) => syncRosterNodeMeta(node));
    renderNodesView();
    if (Array.isArray(state.packets)) {
      renderPackets(state.packets);
    }
    if (Array.isArray(state.chat)) {
      renderChat(state.chat);
    }
  });
}

async function loadPackets() {
  return runSingleFlight("packets", async () => {
    state.packets = await fetchPacketsForVisibleLimit(state.packetLimit);
    setLastPacketReceivedAt(state.packets[0]?.received_at);
    renderPackets(state.packets);
    if (state.nodes.length) {
      renderMap(state.nodes);
    }
  });
}

async function loadRecentActivityPackets() {
  return runSingleFlight("recentActivityPackets", async () => {
    const since = encodeURIComponent(isoMinutesAgo(recentPacketWindowMinutes()));
    state.recentActivityPackets = (await fetchJson(`/api/packets?limit=${MAX_ACTIVITY_PACKETS}&since=${since}`))
      .filter(packetCountsForRecentActivity);
    setLastPacketReceivedAt(state.recentActivityPackets[0]?.received_at);
    if (state.nodes.length) {
      renderMap(state.nodes);
    }
  });
}

async function loadChat() {
  return runSingleFlight("chat", async () => {
    state.chat = await fetchJson(`/api/chat?limit=${CHAT_MESSAGES_LIMIT}`);
    renderChat(state.chat);
  });
}

async function loadMeshSummary() {
  return runSingleFlight("meshSummary", async () => {
    const payload = await fetchJson("/api/mesh/summary");
    renderMeshSummary(payload);
  });
}

async function loadMeshRoutes() {
  return runSingleFlight("meshRoutes", async () => {
    const since = encodeURIComponent(isoMinutesAgo(meshRouteWindowMinutes()));
    const payload = await fetchJson(`/api/mesh/routes?since=${since}`);
    renderMeshRoutes(payload);
  });
}

async function loadAll() {
  const healthResults = await Promise.allSettled([
    loadHealth(),
  ]);
  const results = [
    ...healthResults,
    ...(await Promise.allSettled([
      loadNodes(),
      loadPackets(),
      loadRecentActivityPackets(),
      loadChat(),
      loadMeshSummary(),
      loadMeshRoutes(),
    ])),
  ];
  if (results.some((result) => result.status === "fulfilled")) {
    markUpdated();
  }
  return results
    .filter((result) => result.status === "rejected")
    .map((result) => result.reason);
}

function reportLoadFailures(failures) {
  if (!failures.length) {
    return;
  }
  console.warn("Dashboard load completed with failures.", failures);
}

function startDecayRefreshLoop() {
  if (decayRefreshTimerId != null) {
    return;
  }
  decayRefreshTimerId = window.setInterval(() => {
    if (!state.nodes.length && !state.meshRoutes.routes.length) {
      return;
    }
    renderNodesView();
  }, DECAY_REPAINT_INTERVAL_MS);
}

function handleLoadError(error) {
  state.collectorStatus = {
    connected: false,
    detail: error instanceof Error ? error.message : t("status.unableToLoad"),
    state: "error",
  };
  setSocketState("error");
}

function selectNode(nodeNum, { flyTo = false, openTooltip = false } = {}) {
  const node = nodeByNum(nodeNum);
  if (!node) {
    return;
  }

  state.selectedNodeNum = nodeNum;
  setInspectorOpen(true);
  renderNodesView();

  if (flyTo) {
    centerMapOnNode(node);
  }

  if (openTooltip && nodeHasCoordinates(node)) {
    const marker = mapState.markersByNodeNum.get(nodeNum);
    if (marker) {
      marker.openTooltip();
    }
  }
}

function pulsePanel(element, tone) {
  if (!element) {
    return;
  }
  element.dataset.pulse = tone;
  element.classList.remove("is-live-ping");
  void element.offsetWidth;
  element.classList.add("is-live-ping");
  window.clearTimeout(pulseTimers.get(element));
  pulseTimers.set(element, window.setTimeout(() => {
    element.classList.remove("is-live-ping");
  }, 900));
}

function maybeRefreshSelectedNodeDetail(packet) {
  if (state.selectedNodeNum == null) {
    return false;
  }
  if (
    packet?.from_node_num === state.selectedNodeNum
    || packet?.to_node_num === state.selectedNodeNum
  ) {
    scheduleSelectedNodeDetailRefresh(state.selectedNodeNum);
    return true;
  }
  return false;
}

function recordRecentActivityPacket(packet) {
  if (!packet || !packetCountsForRecentActivity(packet)) {
    return;
  }
  const cutoffMs = Date.now() - (recentPacketWindowMinutes() * 60_000);
  state.recentActivityPackets = [
    packet,
    ...recentActivityPackets().filter((item) => item?.id !== packet.id && (parseUtcDateMs(item?.received_at) || 0) >= cutoffMs),
  ].slice(0, MAX_ACTIVITY_PACKETS);
}

function connectEvents() {
  clearSocketReconnectTimer();
  setSocketState("connecting");
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`);

  socket.addEventListener("open", () => {
    socketReconnectAttempts = 0;
    setSocketState("live");
    if (!state.collectorStatus || !state.perspective) {
      void loadHealth().catch(() => {});
    }
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    markUpdated(payload.ts || new Date().toISOString());
    if (payload.type === "packet_received") {
      setLastPacketReceivedAt(payload.data?.received_at || payload.ts);
      recordRecentActivityPacket(payload.data);
      observePacketNode(payload.data);
      prependPacket(payload.data);
      renderPackets(state.packets);
      maybeRefreshSelectedNodeDetail(payload.data);
      renderNodesView();
      scheduleMeshSummaryRefresh();
      pulsePanel(trafficPanel, "traffic");
      pulsePanel(intelPanel, "nodes");
      if (payload.data.portnum === "TRACEROUTE_APP" || payload.data.portnum === "ROUTING_APP") {
        scheduleMeshRoutesRefresh();
        pulsePanel(mapPanel, "map");
      }
    } else if (payload.type === "chat_message_received") {
      prependChatMessage(payload.data);
      renderChat(state.chat);
      pulsePanel(railToggleChat, "chat");
      pulsePanel(chatPanel, "chat");
    } else if (payload.type === "node_updated") {
      upsertRosterNode(payload.data);
      renderNodesView();
      if (Array.isArray(state.packets)) {
        renderPackets(state.packets);
      }
      if (Array.isArray(state.chat)) {
        renderChat(state.chat);
      }
      scheduleMeshSummaryRefresh();
      pulsePanel(mapPanel, "map");
      pulsePanel(nodesPanel, "nodes");
      pulsePanel(intelPanel, "nodes");
      if (payload.data?.node_num === state.selectedNodeNum) {
        scheduleSelectedNodeDetailRefresh(payload.data.node_num);
      }
    } else if (payload.type === "collector_status") {
      setCollectorStatus(payload.data);
      pulsePanel(collectorCard, "collector");
    }
  });

  socket.addEventListener("close", (event) => {
    if (event.code === SOCKET_POLICY_CLOSE_CODE) {
      clearSocketReconnectTimer();
      setSocketState("blocked");
      return;
    }

    setSocketState("reconnecting");
    if (event.code === SOCKET_TRY_AGAIN_LATER_CLOSE_CODE) {
      socketReconnectAttempts += 1;
      scheduleSocketReconnect(nextOverloadReconnectDelayMs());
      return;
    }

    socketReconnectAttempts = 0;
    scheduleSocketReconnect(SOCKET_FAST_RECONNECT_DELAY_MS);
  });

  socket.addEventListener("error", () => {
    setSocketState("error");
  });
}

function selectNodeFromTarget(target) {
  const nodeTarget = target.closest("[data-node-num]");
  if (!nodeTarget) {
    return;
  }
  const nodeNum = Number(nodeTarget.dataset.nodeNum);
  if (Number.isNaN(nodeNum)) {
    return;
  }
  selectNode(nodeNum, { flyTo: true, openTooltip: true });
}

function renderLocalizedUi() {
  i18n.applyStaticTranslations();
  syncLanguageControls();
  syncThemeControls();
  syncPacketLimitControl();
  renderPerspectiveLabel();
  renderChannelScopedUi();
  renderConnectionIndicator();
  renderStatusBarLegend();
  renderRouteToggle();
  updatePacketFilterButtons();
  updateNodeFilterButtons();
  refreshKpiTicker();

  if (state.meshSummary) {
    renderMeshSummary(state.meshSummary);
  } else {
    updateOverviewStats();
  }
  if (mapState.map || state.nodes.length) {
    renderNodesView();
  } else {
    renderNodeDetail(null);
    renderNodeList();
  }
  if (Array.isArray(state.packets)) {
    renderPackets(state.packets);
  }
  if (Array.isArray(state.chat)) {
    renderChat(state.chat);
  }
}

function initializeStaticUI() {
  state.packetLimit = readStoredPacketLimit() || PACKETS_LIMIT;
  i18n.applyStaticTranslations();
  applyThemeSelection(DEFAULT_UI_THEME);
  renderPerspectiveLabel();
  renderChannelScopedUi();
  renderConnectionIndicator();
  renderStatusBarLegend();
  refreshKpiTicker();
  renderRouteToggle();
  updatePacketFilterButtons();
  updateNodeFilterButtons();
  syncThemeControls();
  syncLanguageControls();
  syncPacketLimitControl();
  setDrawerView("nodes");
  setNodeRailOpen(false);
  setTrafficDrawerOpen(false);
  setInspectorOpen(false);
}

nodeList.addEventListener("click", (event) => {
  selectNodeFromTarget(event.target);
});

packetFilters.addEventListener("click", (event) => {
  const filterButton = event.target.closest("[data-filter]");
  if (!filterButton) {
    return;
  }
  const nextFilter = filterButton.dataset.filter;
  if (!nextFilter || nextFilter === state.packetFilter) {
    return;
  }
  state.packetFilter = nextFilter;
  renderPackets(state.packets);
  queuePacketTopUp();
});

exportPacketsButton?.addEventListener("click", () => {
  exportVisiblePackets();
});

packetLimitSelect?.addEventListener("change", (event) => {
  const nextLimit = normalizePacketLimit(event.target.value);
  if (nextLimit == null || nextLimit === state.packetLimit) {
    syncPacketLimitControl();
    return;
  }
  state.packetLimit = nextLimit;
  writeStoredPacketLimit(nextLimit);
  void loadPackets().catch(handleLoadError);
});

nodeFilters.addEventListener("click", (event) => {
  const filterButton = event.target.closest("[data-node-filter]");
  if (!filterButton) {
    return;
  }
  const nextFilter = filterButton.dataset.nodeFilter;
  if (!nextFilter) {
    return;
  }
  if (state.nodeFilters.has(nextFilter)) {
    state.nodeFilters.delete(nextFilter);
  } else {
    state.nodeFilters.add(nextFilter);
  }
  updateNodeFilterButtons();
  renderNodeList();
  updateOverviewStats();
});

nodeSearch.addEventListener("input", (event) => {
  state.nodeQuery = event.target.value || "";
  renderNodeList();
  updateOverviewStats();
});

chatFeed?.addEventListener("scroll", () => {
  chatStickToBottom = chatIsNearBottom();
  if (!chatStickToBottom) {
    chatPendingScrollBehavior = null;
  }
});

document.addEventListener("visibilitychange", () => {
  flushDeferredRefreshes();
});

routeToggle.addEventListener('click', () => {
  state.showRoutes = !state.showRoutes;
  renderRouteToggle();
  renderMap(state.nodes);
});

refreshDashboard.addEventListener("click", () => {
  clearQueuedRefreshes();
  void loadAll().then(reportLoadFailures).catch(handleLoadError);
});

resetMap.addEventListener("click", () => {
  fitMapToFocus();
});

railToggleNodes?.addEventListener("click", () => {
  if (state.nodesDrawerOpen && state.activeDrawerView === "nodes") {
    setNodeRailOpen(false);
    return;
  }
  setDrawerView("nodes");
  setNodeRailOpen(true);
});

railToggleChat?.addEventListener("click", () => {
  if (state.nodesDrawerOpen && state.activeDrawerView === "chat") {
    setNodeRailOpen(false);
    return;
  }
  setDrawerView("chat");
  setNodeRailOpen(true);
});

railToggleSignals?.addEventListener("click", () => {
  if (state.nodesDrawerOpen && state.activeDrawerView === "signals") {
    setNodeRailOpen(false);
    return;
  }
  setDrawerView("signals");
  setNodeRailOpen(true);
});

railToggleOptions?.addEventListener("click", () => {
  if (state.nodesDrawerOpen && state.activeDrawerView === "options") {
    setNodeRailOpen(false);
    return;
  }
  setDrawerView("options");
  setNodeRailOpen(true);
});

railToggleTraffic?.addEventListener("click", () => {
  setTrafficDrawerOpen(!state.trafficDrawerOpen);
});

uiThemeSelect?.addEventListener("change", (event) => {
  const nextTheme = normalizeThemeId(event.target.value);
  if (!nextTheme) {
    removeStoredThemeId();
    applyThemeSelection(state.uiDefaultTheme);
    return;
  }
  applyThemeSelection(nextTheme, { persist: true });
});

uiLanguageSelect?.addEventListener("change", (event) => {
  const nextLocale = i18n.normalizeLocale(event.target.value);
  if (!nextLocale || nextLocale === i18n.locale()) {
    syncLanguageControls();
    return;
  }
  i18n.setLocale(nextLocale, { persist: true });
  renderLocalizedUi();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || event.defaultPrevented || event.isComposing || event.repeat) {
    return;
  }
  if (activeElementIsEditable()) {
    return;
  }
  if (dismissTopmostLayer()) {
    event.preventDefault();
  }
});

/* Drawer close buttons (mobile) */
document.querySelectorAll(".drawer-close").forEach((btn) => {
  btn.addEventListener("click", () => {
    const drawer = btn.dataset.drawer;
    if (drawer === "rail") setNodeRailOpen(false);
    else if (drawer === "traffic") setTrafficDrawerOpen(false);
    else if (drawer === "inspector") clearSelectedNode();
  });
});

/* Search toggle removed — search bar always visible (N-02) */

closeInspectorBtn?.addEventListener("click", () => {
  clearSelectedNode();
});

initializeStaticUI();

loadAll()
  .then((failures) => {
    startDecayRefreshLoop();
    connectEvents();
    reportLoadFailures(failures);
  })
  .catch(handleLoadError);
