const BROADCAST_NODE_NUM = 4294967295;

const collectorCard = document.getElementById("collector-card");
const collectorDetail = document.getElementById("collector-detail");
const perspectiveLabel = document.getElementById("perspective-label");
const kpiTicker = document.getElementById("kpi-ticker");
const statsRow = document.getElementById("stats-row");
const nodesPanelCount = document.getElementById("nodes-panel-count");
const intelPanelCount = document.getElementById("intel-panel-count");
const mapRoot = document.getElementById("leaflet-map");
const mapEmpty = document.getElementById("map-empty");
const mapNote = document.getElementById("map-note");
const mapLegendCopy = document.getElementById("map-legend-copy");
const nodeDetail = document.getElementById("node-detail");
const nodeList = document.getElementById("node-list");
const intelGrid = document.getElementById("intel-grid");
const intelStory = document.getElementById("intel-story");
const chatFeed = document.getElementById("chat-feed");
const packetsBody = document.getElementById("packets-body");
const refreshDashboard = document.getElementById("refresh-dashboard");
const resetMap = document.getElementById("reset-map");
const packetFilters = document.getElementById("packet-filters");
const nodeFilters = document.getElementById("node-filters");
const nodeSearch = document.getElementById("node-search");
const routeToggle = document.getElementById("route-toggle");
const mapPanel = document.getElementById("mesh-map");
const nodesPanel = document.getElementById("mesh-nodes");
const intelPanel = document.getElementById("mesh-intel");
const chatPanel = document.getElementById("mesh-chat");
const trafficPanel = document.getElementById("mesh-traffic");

const mapViewport = document.querySelector(".map-viewport");
const nodeRail = document.getElementById("node-rail");
const inspectorPanel = document.querySelector(".inspector-shell");
const closeInspectorBtn = document.getElementById("close-inspector");
const railToggleNodes = document.getElementById("rail-toggle-nodes");
const railToggleChat = document.getElementById("rail-toggle-chat");
const railToggleSignals = document.getElementById("rail-toggle-signals");
const railToggleTraffic = document.getElementById("rail-toggle-traffic");
const rosterToolbar = document.getElementById("roster-toolbar");

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const wholeNumberFormatter = new Intl.NumberFormat(undefined);

const NODE_DECAY_WINDOW_MINUTES = 24 * 60;
const DECAY_REPAINT_INTERVAL_MS = 60_000;
const DEFAULT_RECENT_ACTIVITY_WINDOW_MINUTES = 60;
const DEFAULT_NODE_ACTIVE_WINDOW_MINUTES = 180;
const NETWORK_ROUTE_WINDOW_MINUTES = 7 * 24 * 60;
const SELECTED_ROUTE_WINDOW_MINUTES = 7 * 24 * 60;
const PACKETS_LIMIT = 40;
const CHAT_MESSAGES_LIMIT = 60;
const NODE_DETAIL_RECENT_PACKETS_LIMIT = 20;
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
};

const mapState = {
  map: null,
  routeLayer: null,
  markerLayer: null,
  markersByNodeNum: new Map(),
  routeLinesByKey: new Map(),
  initialViewApplied: false,
  zoomListenerBound: false,
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

function formatTime(value) {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return timeFormatter.format(date);
}

function formatRelativeTime(value, nowMs = Date.now()) {
  const ageMinutes = ageMinutesSince(value, nowMs);
  if (ageMinutes == null) {
    return "n/a";
  }
  if (ageMinutes < 1) {
    return "Just now";
  }
  if (ageMinutes < 60) {
    return `${Math.floor(ageMinutes)}m ago`;
  }
  if (ageMinutes < 24 * 60) {
    return `${Math.floor(ageMinutes / 60)}h ago`;
  }
  if (ageMinutes < 7 * 24 * 60) {
    return `${Math.floor(ageMinutes / (24 * 60))}d ago`;
  }
  return formatTime(value);
}

function formatLastUpdated(value) {
  if (!value) {
    return "Waiting";
  }
  return formatTime(value);
}

function formatNumber(value, digits = 1, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatWholeNumber(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return wholeNumberFormatter.format(Math.round(Number(value)));
}

function formatCompactChange(value, digits = 0, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return `${Math.abs(Number(value)).toFixed(digits)}${suffix}`;
}

function formatCoordinate(value, axis) {
  if (value == null || Number.isNaN(Number(value))) {
    return "n/a";
  }
  const hemisphere = axis === "lat"
    ? (value >= 0 ? "N" : "S")
    : (value >= 0 ? "E" : "W");
  return `${Math.abs(Number(value)).toFixed(4)}° ${hemisphere}`;
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
  return node?.short_name || node?.long_name || node?.node_id || `Node ${node?.node_num ?? "?"}`;
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
  return `Node ${node.node_num}`;
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
    limit: PACKETS_LIMIT,
    keyFor: packetKey,
  });
}

function prependChatMessage(message) {
  state.chat = prependUniqueItem(state.chat, message, {
    limit: CHAT_MESSAGES_LIMIT,
    keyFor: chatMessageKey,
  });
}

function patchNodeDetailRecentPackets(nodeNum, packet) {
  const detailPayload = state.nodeDetails.get(nodeNum);
  if (!detailPayload) {
    return;
  }
  state.nodeDetails.set(nodeNum, {
    ...detailPayload,
    recent_packets: prependUniqueItem(detailPayload.recent_packets, packet, {
      limit: NODE_DETAIL_RECENT_PACKETS_LIMIT,
      keyFor: packetKey,
    }),
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
      activity_count_60m: 1,
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
  existing.activity_count_60m = intValue(existing.activity_count_60m) + 1;
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
  return packet?.path_label || "Unknown";
}

function packetPathDetails(packet) {
  if (!packet) {
    return "";
  }

  if (packetPathTone(packet) === "mqtt") {
    return "Seen via MQTT bridge";
  }
  const hops = packetHopsTaken(packet);
  if (hops === 0) {
    return "Heard by receiver without relay";
  }
  if (hops === 1) {
    return "Arrived after 1 relay hop";
  }
  if (hops != null) {
    return `Arrived after ${hops} relay hops`;
  }
  return "";
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

function nodePathLabel(node) {
  const status = nodeStatus(node);
  if (status === "local") {
    return "Receiver";
  }
  if (status === "mqtt") {
    return "MQTT";
  }
  if (node?.hops_away == null) {
    return "Path Unknown";
  }
  if (Number(node.hops_away) <= 1) {
    return "Direct";
  }
  if (Number(node.hops_away) === 2) {
    return "2 Hops";
  }
  return `${Number(node.hops_away)} Hops`;
}

function nodePathDescription(node) {
  const status = nodeStatus(node);
  if (status === "local") {
    return "Receiver-local node";
  }
  if (status === "mqtt") {
    return "Observed through an MQTT bridge";
  }
  if (node?.hops_away == null) {
    return "No passive path estimate yet";
  }
  if (Number(node.hops_away) <= 1) {
    return "Direct RF path from this receiver";
  }
  return `${Number(node.hops_away)} hops away from this receiver`;
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

function routeAgeMinutes(route, nowMs = Date.now()) {
  return ageMinutesSince(route?.latest_received_at || route?.received_at, nowMs);
}

function groupedMeshRoutes() {
  const groupedRoutes = new Map();
  state.meshRoutes.routes.forEach((route) => {
    const key = routeIdentityKey(route);
    const existing = groupedRoutes.get(key);
    if (!existing) {
      groupedRoutes.set(key, {
        ...route,
        group_key: key,
        count: 1,
        latest_received_at: route.received_at || null,
      });
      return;
    }

    existing.count += 1;
    if ((route.received_at || "") > (existing.latest_received_at || "")) {
      existing.latest_received_at = route.received_at || existing.latest_received_at;
      existing.received_at = route.received_at || existing.received_at;
      existing.packet_id = route.packet_id || existing.packet_id;
      existing.mesh_packet_id = route.mesh_packet_id || existing.mesh_packet_id;
    }
  });
  return [...groupedRoutes.values()].sort((left, right) => {
    const leftSeen = left.latest_received_at || "";
    const rightSeen = right.latest_received_at || "";
    if (leftSeen !== rightSeen) {
      return rightSeen.localeCompare(leftSeen);
    }
    return intValue(right.count) - intValue(left.count);
  });
}

function routeSelected(route) {
  return state.selectedNodeNum != null && route.path_node_nums.includes(state.selectedNodeNum);
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

function visibleMeshRoutes(nowMs = Date.now()) {
  return groupedMeshRoutes().filter((route) => routeLatLngs(route, nowMs));
}

function activeMeshRoutes(nowMs = Date.now()) {
  if (!state.showRoutes) {
    return [];
  }
  return visibleMeshRoutes(nowMs).filter((route) => {
    const ageMinutes = routeAgeMinutes(route, nowMs);
    if (ageMinutes == null) {
      return false;
    }
    return ageMinutes <= (routeSelected(route) ? SELECTED_ROUTE_WINDOW_MINUTES : NETWORK_ROUTE_WINDOW_MINUTES);
  });
}

function routeStyle(route, ctx) {
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
  return {
    color: isSelected ? "#fff3db" : "#e8a94d",
    weight: isSelected ? Math.min(baseWeight + 1.0, 5.2) : baseWeight,
    opacity: isSelected ? 0.98 : (dimmedRoute ? Math.min(baseOpacity * 0.15, 0.06) : baseOpacity),
    dashArray: route.direction === "return" ? "12 10" : null,
    lineCap: "round",
    lineJoin: "round",
  };
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
    return "LIVE";
  }
  if (freshness === "warm") {
    return "RECENT";
  }
  if (freshness === "stale") {
    return "STALE";
  }
  return "SEEN";
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
    return "Broadcast";
  }
  const node = nodeByNum(packet.to_node_num);
  return node ? nodeLabel(node) : `Node ${packet.to_node_num}`;
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
    return { tone: "none", symbol: "—", detail: "No baseline" };
  }
  const delta = currentValue - previousValue;
  if (Math.abs(delta) < 0.0001) {
    return { tone: "flat", symbol: "→", detail: "Flat" };
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
    return "No baseline";
  }
  if (trend.tone === "flat") {
    return context ? `Flat vs prior ${context}` : "Flat";
  }
  return context ? `${trend.detail} vs prior ${context}` : trend.detail;
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
    return "No fresh path read";
  }
  if (mqttShare != null && mqttShare >= 30) {
    return "MQTT-heavy";
  }
  if (relayShare != null && relayShare >= 40) {
    return "Relay heavy";
  }
  if (directShare != null && relayShare != null && directShare >= 55 && directShare >= (relayShare + 10)) {
    return "Mostly direct";
  }
  return "Mixed paths";
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
  const meshPaths = intValue(state.meshRoutes?.stats?.total);

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
    statPaths.textContent = meshPaths ? formatWholeNumber(meshPaths) : "--";
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

function intelMeter(title, headline, segments, emptyLabel = "No passive traffic yet.") {
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
        <span class="mono-text">${escapeHtml(total ? `${formatWholeNumber(total)} total` : "Waiting")}</span>
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

function receiverMetricDetail(receiver) {
  if (!receiver || receiver.node_num == null) {
    return "Waiting for receiver identity";
  }
  if (receiver.updated_at) {
    return `${receiver.label || `Node ${receiver.node_num}`} · ${formatTime(receiver.updated_at)}`;
  }
  return `${receiver.label || `Node ${receiver.node_num}`} · Telemetry pending`;
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

function receiverSparklineGeometry(series, width = 212, height = 54, padding = 4) {
  if (!series.length) {
    return null;
  }

  const plottingSeries = series.length === 1 ? [series[0], series[0]] : series;
  const values = plottingSeries.map((sample) => sample.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue;
  const innerWidth = width - (padding * 2);
  const innerHeight = height - (padding * 2);
  const baselineY = height - padding;

  const points = plottingSeries.map((sample, index) => {
    const x = padding + ((innerWidth * index) / Math.max(plottingSeries.length - 1, 1));
    const y = range === 0
      ? padding + (innerHeight / 2)
      : padding + (((maxValue - sample.value) / range) * innerHeight);
    return { x, y };
  });

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
    maxValue,
  };
}

function receiverSparkline(label, tone, series) {
  if (!series.length) {
    return "";
  }

  const geometry = receiverSparklineGeometry(series);
  if (!geometry) {
    return "";
  }

  return `
    <div class="receiver-sparkline-frame ${tone}">
      <svg
        class="receiver-sparkline-graphic"
        viewBox="0 0 212 54"
        aria-label="${escapeHtml(`${label} history`)}"
        role="img"
      >
        <path class="receiver-sparkline-area" d="${geometry.areaPath}"></path>
        <path class="receiver-sparkline-line" d="${geometry.linePath}"></path>
        <circle class="receiver-sparkline-dot" cx="${geometry.lastX}" cy="${geometry.lastY}" r="3.5"></circle>
      </svg>
    </div>
  `;
}

function receiverTelemetryPanel(label, currentValue, key, tone, receiver) {
  const series = receiverHistorySeries(receiver, key);
  const geometry = receiverSparklineGeometry(series);
  const peakValue = geometry ? formatNumber(geometry.maxValue, 1, "%") : null;
  const meta = peakValue
    ? `Peak ${peakValue} · ${formatWholeNumber(series.length)} ${series.length === 1 ? "sample" : "samples"}`
    : "";

  return `
    <section class="receiver-metric ${tone}">
      <span class="receiver-metric-label">${escapeHtml(label)}</span>
      <strong class="receiver-metric-value">${escapeHtml(formatNumber(currentValue, 1, "%"))}</strong>
      ${meta ? `<span class="receiver-metric-meta mono-text">${escapeHtml(meta)}</span>` : ""}
      ${series.length && geometry ? `
        <div class="receiver-sparkline-frame ${tone}">
          <svg class="receiver-sparkline-graphic" viewBox="0 0 212 54" aria-label="${escapeHtml(`${label} history`)}" role="img">
            <path class="receiver-sparkline-area" d="${geometry.areaPath}"></path>
            <path class="receiver-sparkline-line" d="${geometry.linePath}"></path>
            <circle class="receiver-sparkline-dot" cx="${geometry.lastX}" cy="${geometry.lastY}" r="3.5"></circle>
          </svg>
        </div>
      ` : ""}
    </section>
  `;
}

function channelUtilizationBlock(receiver) {
  const recLabel = receiver?.label || (receiver?.node_num != null ? `Node ${receiver.node_num}` : null);
  const recTime = receiver?.updated_at ? formatTime(receiver.updated_at) : null;
  const sectionParts = ["Channel utilization"];
  if (recLabel) sectionParts.push(recLabel);
  if (recTime) sectionParts.push(recTime);

  return `
    <div class="signals-section">
      <span class="signals-section-label">${escapeHtml(sectionParts.join(" · "))}</span>
      <div class="receiver-metric-grid">
        ${receiverTelemetryPanel("Ch. util", receiver?.channel_utilization, "channel_utilization", "channel", receiver)}
        ${receiverTelemetryPanel("Air util TX", receiver?.air_util_tx, "air_util_tx", "air", receiver)}
      </div>
    </div>
  `;
}

function metric(label, value, tone = "") {
  return `
    <div class="hud-metric${tone ? ` ${tone}` : ""}">
      <span class="hud-metric-label">${escapeHtml(label)}</span>
      <span class="hud-metric-value">${escapeHtml(value)}</span>
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
    return meshIsStale() ? "Stale" : "Live";
  }
  if (state.socketState === "connecting") {
    return "Connecting";
  }
  if (state.socketState === "reconnecting") {
    return "Reconnecting";
  }
  if (state.socketState === "blocked") {
    return "Blocked";
  }
  if (state.collectorStatus && !state.collectorStatus.connected) {
    return "Offline";
  }
  if (state.socketState === "error") {
    return "Degraded";
  }
  return "Offline";
}

function connectionStateDetail() {
  const updatedText = state.lastUpdatedAt
    ? `Last update ${formatLastUpdated(state.lastUpdatedAt)}`
    : "No live updates yet";
  const packetText = state.lastPacketReceivedAt
    ? `Last packet ${formatTime(state.lastPacketReceivedAt)}`
    : "No packets heard yet";

  if (receiverLinkActive()) {
    if (meshIsStale()) {
      return `Link active but no fresh observations. ${packetText}. ${updatedText}.`;
    }
    return `Receiver link active. ${packetText}. ${updatedText}.`;
  }

  if (state.collectorStatus?.detail) {
    return `${state.collectorStatus.detail}. ${packetText}. ${updatedText}.`;
  }

  if (state.collectorStatus && !state.collectorStatus.connected) {
    return `Receiver link unavailable. ${packetText}. ${updatedText}.`;
  }

  if (state.socketState === "reconnecting") {
    return `Event stream reconnecting. ${packetText}. ${updatedText}.`;
  }

  if (state.socketState === "connecting") {
    return `Opening event stream. ${packetText}. ${updatedText}.`;
  }

  if (state.socketState === "blocked") {
    return `Event stream blocked by server policy. ${packetText}. ${updatedText}.`;
  }

  if (state.socketState === "error") {
    return `Stream error. ${packetText}. ${updatedText}.`;
  }

  return `Waiting for receiver status. ${packetText}. ${updatedText}.`;
}

function renderPerspectiveLabel() {
  if (!perspectiveLabel) {
    return;
  }
  if (!state.perspective) {
    perspectiveLabel.textContent = "Receiver pending";
    return;
  }
  const label = state.perspective.label || "Receiver";
  const localNodeNum = state.perspective.local_node_num;
  perspectiveLabel.textContent = localNodeNum == null
    ? label
    : `${label} · RX ${localNodeNum}`;
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
    return "Text";
  }
  if (category === "position") {
    return "Pos";
  }
  if (category === "telemetry") {
    return "Telem";
  }
  if (category === "admin") {
    return "Admin";
  }
  return "Other";
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
    if (route.path_node_nums.includes(state.selectedNodeNum)) {
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
    mapNote.textContent = "Route overlays are hidden.";
    return;
  }
  if (!activeMeshRoutes().length) {
    mapNote.hidden = false;
    mapNote.textContent = "No route overlays available for the current node set.";
    return;
  }
  mapNote.hidden = true;
  mapNote.textContent = "";
}

function routeModeSummary(routes) {
  if (!state.showRoutes) {
    return "Routes hidden";
  }

  if (!routes.length) {
    return "No routes in scope";
  }

  return `${formatWholeNumber(routes.length)} mesh ${routes.length === 1 ? "path" : "paths"}`;
}

function updateOverviewStats() {
  const nodeTotal = state.nodes.length;
  const activeCount = state.nodes.filter((n) => nodeIsActive(n)).length;

  if (nodesPanelCount) {
    nodesPanelCount.textContent = `${formatWholeNumber(nodeTotal)} heard · ${formatWholeNumber(activeCount)} active`;
  }
  renderMapHud();
}

function packetDirectionLabel(packet, nodeNum) {
  if (packet.from_node_num === nodeNum) {
    return `TX -> ${toNodeLabel(packet)}`;
  }
  if (packet.to_node_num === nodeNum) {
    return `RX <- ${fromNodeLabel(packet)}`;
  }
  return `${fromNodeLabel(packet)} -> ${toNodeLabel(packet)}`;
}

function renderNodeDetail(node) {
  if (!node) {
    nodeDetail.innerHTML = `
      <div class="hud-empty">
        <h3>No Node Selected</h3>
        <p>Select a node from the map or roster when positions arrive.</p>
      </div>
    `;
    return;
  }

  const detailPayload = state.nodeDetails.get(node.node_num);
  const recentPackets = detailPayload?.recent_packets?.slice(0, 3) || [];
  const insights = detailPayload?.insights || null;
  const loading = state.nodeDetailLoadingNodeNum === node.node_num;
  const hasError = state.nodeDetailErrorNodeNum === node.node_num;
  const freshness = nodeFreshness(node);
  const hudTone = freshness;
  const pathLabel = nodePathLabel(node);
  const roleLabel = [node.role, node.hardware_model].filter(Boolean).join(" / ") || "Node";

  nodeDetail.innerHTML = `
    <div class="node-hud-card ${hudTone}">
      <div class="node-hud-head">
        <div>
          <h3>${escapeHtml(nodeLabel(node))}</h3>
          <p class="node-hud-subtitle">${escapeHtml(`${roleLabel} · ${nodePathDescription(node)}`)}</p>
        </div>
        <div class="node-hud-state ${hudTone}">${escapeHtml(freshnessLabel(node))}</div>
      </div>

      <div class="node-hud-metrics">
        ${metric("Path", pathLabel)}
        ${metric("Hops Away", node.hops_away ?? "n/a")}
        ${metric("Last Heard", formatTime(node.last_heard_at))}
        ${metric("SNR", formatNumber(node.last_snr, 1, " dB"), freshness === "stale" ? "muted" : "")}
        ${metric("Packets Heard", formatWholeNumber(insights?.heard_packets))}
        ${metric("Battery", node.battery_level == null ? "n/a" : `${Math.round(node.battery_level)}%`)}
        ${metric("Latitude", formatCoordinate(node.latitude, "lat"))}
        ${metric("Longitude", formatCoordinate(node.longitude, "lon"))}
      </div>

      <div class="node-hud-activity">
        <div class="node-hud-activity-head">
          <span>Recent Activity</span>
          <span class="mono-text">Node Detail</span>
        </div>

        ${loading ? `
          <div class="hud-empty compact">
            <p>Loading recent node activity...</p>
          </div>
        ` : ""}

        ${!loading && hasError ? `
          <div class="hud-empty compact">
            <p>Unable to load recent node activity.</p>
          </div>
        ` : ""}

        ${!loading && !hasError && !recentPackets.length ? `
          <div class="hud-empty compact">
            <p>No recent packets for this node yet.</p>
          </div>
        ` : ""}

        ${!loading && !hasError && recentPackets.length ? `
          <div class="node-hud-activity-list">
            ${recentPackets.map((packet) => `
              <article class="node-hud-activity-row">
                <div class="node-hud-activity-top">
                  <span class="port-badge ${portCategory(packet.portnum)}">${escapeHtml(portBadgeText(packet.portnum))}</span>
                  <span class="mono-text">${escapeHtml(formatTime(packet.received_at))}</span>
                </div>
                <div class="node-hud-activity-route">${escapeHtml(`${packetDirectionLabel(packet, node.node_num)} · ${packetPathLabel(packet)}`)}</div>
                <p class="node-hud-activity-preview">${escapeHtml(packet.text_preview || packetPathDetails(packet) || "No text preview")}</p>
              </article>
            `).join("")}
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

function nodeRowChromeStyle(node, nowMs = Date.now()) {
  const decay = nodeDecayFraction(node, nowMs);
  const borderAlpha = interpolate(0.2, 0.08, decay);
  const hoverBorderAlpha = interpolate(0.28, 0.12, decay);
  const backgroundAlpha = interpolate(0.82, 0.52, decay);
  const hoverBackgroundAlpha = interpolate(0.92, 0.62, decay);
  return [
    `--node-row-border: rgba(91, 112, 121, ${borderAlpha.toFixed(3)})`,
    `--node-row-hover-border: rgba(152, 170, 178, ${hoverBorderAlpha.toFixed(3)})`,
    `--node-row-bg: rgba(13, 28, 34, ${backgroundAlpha.toFixed(3)})`,
    `--node-row-hover-bg: rgba(17, 35, 42, ${hoverBackgroundAlpha.toFixed(3)})`,
  ].join("; ");
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
    nodeList.innerHTML = `
      <div class="node-list-empty">
        <h3>${hasFilters ? "No Matching Nodes" : "No Nodes Yet"}</h3>
        <p>${hasFilters ? "Adjust the roster filters or search query to widen the view." : "LongFast nodes appear here as the receiver hears them."}</p>
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
        const hops = Number(node.hops_away);
        const isDirect = proxTone === "direct";
        const hopPill = isDirect
          ? ""
          : (status === "mqtt"
            ? `<span class="node-row-hop">MQTT</span>`
            : (node.hops_away != null
              ? `<span class="node-row-hop">${hops} ${hops === 1 ? "hop" : "hops"}</span>`
              : ""));
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
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd",
    maxZoom: 20,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO',
  }).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd",
    maxZoom: 20,
    opacity: 0.4,
    pane: "overlayPane",
  }).addTo(map);

  const routePane = map.createPane("mesh-routes");
  routePane.style.zIndex = "340";
  routePane.style.pointerEvents = "none";

  mapState.routeLayer = L.layerGroup().addTo(map);
  mapState.markerLayer = L.layerGroup();
  mapState.markerLayer.addTo(map);
  mapState.map = map;
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
  const nowMs = ctx.nowMs;
  const neighborhood = ctx.neighborhood;
  const degreeMap = ctx.degreeMap;
  const isSelected = node.node_num === state.selectedNodeNum;
  const active = nodeIsWindowActive(node, nowMs);
  const direct = isDirectNode(node);
  const type = nodeType(node);
  const significance = degreeMap ? nodeSignificance(node, degreeMap) : clamp(nodeActivityCount(node) / 6, 0, 1);
  const size = Math.round(
    interpolate(14, 32, significance)
    + (active ? 2 : 0)
    + (isSelected ? 4 : 0)
  );
  const baseOpacity = clamp(nodeSignalOpacity(node, nowMs) + (active ? 0.08 : 0), NODE_MIN_OPACITY, 0.98);
  const dimmed = neighborhood != null && !neighborhood.has(node.node_num);
  const opacity = dimmed ? clamp(baseOpacity * 0.25, 0.06, 0.20) : baseOpacity;
  return {
    size,
    opacity,
    type,
    fillColor: "#e8a94d",
    glyphColor: "#2f1a03",
    borderColor: isSelected ? "#fff3db" : (direct ? "#f5b862" : "#c49455"),
    borderWidth: isSelected ? 3.1 : (direct ? 2.2 : 1.8),
    haloColor: isSelected ? "rgba(255, 243, 219, 0.35)" : (active ? "rgba(232, 169, 77, 0.35)" : "rgba(232, 169, 77, 0.18)"),
    haloOpacity: dimmed ? 0.15 : (isSelected || active ? 1 : 0.7),
    fillOpacity: dimmed ? 0.3 : (active ? 0.9 : 0.78),
  };
}

function nodeGlyphMarkup(_type, _color) {
  return "";
}

function markerIcon(node, ctx) {
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
    ? `<span class="node-marker-label" style="color:#e8dcc8">${escapeHtml(node.short_name)}</span>`
    : "";
  return L.divIcon({
    className: "",
    html: `
      <div class="node-marker-shell" style="width:${size}px;opacity:${style.opacity.toFixed(3)};">
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
        ${labelHtml}
      </div>
    `,
    iconSize: [size, size + labelHeight],
    iconAnchor: [size / 2, size / 2],
    tooltipAnchor: [0, -(size / 2)],
  });
}

function popupMarkup(node) {
  const roleHardware = [node.role, node.hardware_model].filter(Boolean).join(" / ") || "Node telemetry";
  return `
    <div class="mesh-node-tooltip-card">
      <div class="mesh-node-tooltip-title">${escapeHtml(nodeLabel(node))}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(roleHardware)}</div>
      <div class="mesh-node-tooltip-line">${escapeHtml(nodePathDescription(node))}</div>
      <div class="mesh-node-tooltip-line">Last heard ${escapeHtml(formatTime(node.last_heard_at))}</div>
      <div class="mesh-node-tooltip-line">SNR ${escapeHtml(formatNumber(node.last_snr, 1, " dB"))}</div>
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
    chatPanel.hidden = !chatVisible;
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
  if (chatVisible && chatPendingScrollBehavior) {
    scheduleChatScrollToBottom(chatPendingScrollBehavior);
  }
}

function setDrawerView(nextView) {
  state.activeDrawerView = nextView === "signals" || nextView === "chat" ? nextView : "nodes";
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

function renderMapHud() {}

function renderRouteToggle() {
  if (!routeToggle) {
    return;
  }
  routeToggle.textContent = state.showRoutes ? 'Hide Routes' : 'Show Routes';
  routeToggle.setAttribute('aria-pressed', String(state.showRoutes));
}

function renderMap(items) {
  const nowMs = Date.now();
  const mappedNodes = sortNodes(items).filter((node) => nodeHasCoordinates(node) && nodeIsVisible(node, nowMs));
  const map = ensureMap();
  const routes = activeMeshRoutes(nowMs);
  if (mapLegendCopy) {
    mapLegendCopy.textContent = routeModeSummary(routes);
  }
  renderRouteToggle();
  renderMapNotes();

  if (!mappedNodes.length) {
    state.remoteNodeNums = new Set();
    mapEmpty.textContent = state.nodes.some(nodeHasCoordinates)
      ? "No mapped nodes heard in the last 24 hours."
      : "Waiting for LongFast node locations.";
    mapEmpty.hidden = false;
    mapNote.hidden = true;
    mapNote.textContent = "";
    if (mapState.routeLayer) {
      mapState.routeLayer.clearLayers();
      mapState.routeLinesByKey.clear();
    }
    if (mapState.markerLayer) {
      mapState.markerLayer.clearLayers();
      mapState.markersByNodeNum.clear();
    }
    updateOverviewStats();
    return;
  }

  const neighborhood = selectedNeighborhood(routes);
  const degreeMap = computeRouteDegreeMap(routes);
  const zoom = map.getZoom();
  const ctx = { nowMs, neighborhood, degreeMap, zoom };

  state.remoteNodeNums = new Set();
  mapEmpty.textContent = "Waiting for LongFast node locations.";
  mapEmpty.hidden = true;
  mapState.routeLayer.clearLayers();
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
    .filter((route) => state.selectedNodeNum != null && route.path_node_nums.includes(state.selectedNodeNum))
    .map((route) => mapState.routeLinesByKey.get(routeKey(route)))
    .filter(Boolean);
  selectedRoutes.forEach((line) => line.bringToFront());

  if (!mapState.initialViewApplied) {
    fitMapToFocus();
  } else {
    map.invalidateSize();
  }

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
  const unknownPackets = Math.max(0, totalPackets - directPackets - relayedPackets - mqttPackets);
  const textPackets = intValue(traffic.text);
  const positionPackets = intValue(traffic.position);
  const telemetryPackets = intValue(traffic.telemetry);
  const otherPackets = Math.max(0, totalPackets - textPackets - positionPackets - telemetryPackets);
  const coverageShare = sharePercentage(mappedNodes, totalNodes);
  const directShare = sharePercentage(directPackets, totalPackets);

  const pathSegments = [
    { label: "Direct RF", value: directPackets, tone: "direct" },
    { label: "Relayed", value: relayedPackets, tone: "relayed" },
    { label: "MQTT", value: mqttPackets, tone: "mqtt" },
    { label: "Unknown", value: unknownPackets, tone: "unknown" },
  ];
  const dominantPath = dominantSegment(pathSegments);

  if (intelPanelCount) {
    intelPanelCount.textContent = `${formatWholeNumber(totalPackets)} total packets`;
  }

  // Block 1 — Coverage: 2-column metric grid
  intelGrid.innerHTML = [
    intelStat(
      "Heard nodes",
      formatWholeNumber(totalNodes),
      totalNodes ? `${formatWholeNumber(mappedNodes)} mapped` : "Waiting for nodes",
      "heard-accent"
    ),
    intelStat(
      "Coverage",
      totalNodes ? `${coverageShare}%` : "—",
      totalNodes ? `${formatWholeNumber(mappedNodes)} of ${formatWholeNumber(totalNodes)}` : "No node roster yet"
    ),
  ].join("");

  if (!totalPackets && !totalNodes) {
    intelStory.innerHTML = `
      ${channelUtilizationBlock(receiver)}
      <div class="hud-empty compact">
        <p>Waiting for passive mesh traffic to build an intel view.</p>
      </div>
    `;
    updateOverviewStats();
    return;
  }

  // Block 2 — Routing health: 3 KV rows
  const dominantLabel = dominantPath
    ? `${sharePercentage(dominantPath.value, totalPackets)}% ${dominantPath.label.toLowerCase()}`
    : "Waiting";
  const routingHealthHtml = `
    <div class="signals-section">
      <span class="signals-section-label">Routing health</span>
      <div class="routing-health">
        ${routingHealthRow("Dominant path", dominantLabel)}
        ${routingHealthRow("Direct RF", directPackets ? `${directShare}% · ${formatWholeNumber(directPackets)} pkts` : "No direct traffic")}
        ${routingHealthRow("Total packets", formatWholeNumber(totalPackets))}
      </div>
    </div>
  `;

  // Block 3 — Packet breakdown: proportional bars
  const breakdownTypes = [
    { label: "ACK only", value: otherPackets, tone: "ack" },
    { label: "Telemetry", value: telemetryPackets, tone: "telemetry" },
    { label: "Position", value: positionPackets, tone: "position" },
  ];
  const maxBreakdown = Math.max(...breakdownTypes.map((t) => t.value), 1);

  const breakdownHtml = `
    <div class="signals-section">
      <span class="signals-section-label">Packet breakdown</span>
      <div class="packet-breakdown">
        ${breakdownTypes.map((t) => {
          const barPct = Math.round((t.value / maxBreakdown) * 100);
          return `
            <div class="breakdown-row">
              <span class="breakdown-label">${escapeHtml(t.label)}</span>
              <span class="breakdown-bar"><span class="breakdown-bar-fill ${t.tone}" style="width:${barPct}%"></span></span>
              <span class="breakdown-count mono-text">${formatWholeNumber(t.value)}</span>
            </div>
          `;
        }).join("")}
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
  }
  // Update paths stat in top bar (T-06)
  refreshKpiTicker();
}

function packetRowMarkup(packet) {
  const category = portCategory(packet.portnum);
  const hops = packetHopsTaken(packet);
  const pathTone = packetPathTone(packet);
  const isMqtt = pathTone === "mqtt";
  const isUnknown = hops == null && !isMqtt;
  const isHighHop = hops != null && hops >= 4;
  const pathCellClass = isHighHop ? " path-cell-high" : "";

  const fromName = fromNodeLabel(packet);
  const fromId = packet.from_node_num != null ? `#${packet.from_node_num}` : "";

  const pathContent = `<span class="path-badge ${pathTone}">${escapeHtml(isUnknown ? "Unknown" : packetPathLabel(packet))}</span>`;

  const previewText = packet.text_preview;
  const previewHtml = previewText
    ? `<td class="preview-cell">${escapeHtml(previewText)}</td>`
    : `<td class="preview-cell preview-cell--empty">\u2014</td>`;

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
          <span class="table-node-sub mono-text">${escapeHtml(packet.to_node_num === BROADCAST_NODE_NUM ? "BROADCAST" : `#${packet.to_node_num ?? "n/a"}`)}</span>
        </div>
      </td>
      <td>
        <div class="port-cell">
          <span class="port-badge ${category}">${escapeHtml(portBadgeText(packet.portnum))}</span>
        </div>
      </td>
      <td class="${pathCellClass}">
        <div class="port-cell">${pathContent}</div>
      </td>
      ${previewHtml}
    </tr>
  `;
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
  const filteredItems = items.filter(packetFilterMatches);
  updatePacketFilterButtons();

  if (!filteredItems.length) {
    packetsBody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-cell">No packets match the current filter.</td>
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
    chatFeed.innerHTML = `
      <div class="chat-empty">
        <h3>No Chat Yet</h3>
        <p>Broadcast LongFast messages will stream here when heard by this receiver.</p>
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
    throw new Error(`Request failed: ${response.status}`);
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
    setCollectorStatus(payload.collector);
    setPerspective(payload.perspective);
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
    state.packets = await fetchJson(`/api/packets?limit=${PACKETS_LIMIT}`);
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
    state.recentActivityPackets = await fetchJson(`/api/packets?limit=${MAX_ACTIVITY_PACKETS}&since=${since}`);
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
  const results = await Promise.allSettled([
    loadHealth(),
    loadNodes(),
    loadPackets(),
    loadRecentActivityPackets(),
    loadChat(),
    loadMeshSummary(),
    loadMeshRoutes(),
  ]);
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
    detail: error instanceof Error ? error.message : "Unable to load dashboard",
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
    patchNodeDetailRecentPackets(state.selectedNodeNum, packet);
    scheduleSelectedNodeDetailRefresh(state.selectedNodeNum);
    return true;
  }
  return false;
}

function recordRecentActivityPacket(packet) {
  if (!packet) {
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
      if (
        payload.data.portnum === "TEXT_MESSAGE_APP"
        && payload.data.text_preview
        && payload.data.to_node_num === BROADCAST_NODE_NUM
      ) {
        prependChatMessage(payload.data);
        renderChat(state.chat);
      }
      renderNodesView();
      scheduleMeshSummaryRefresh();
      pulsePanel(trafficPanel, "traffic");
      pulsePanel(intelPanel, "nodes");
      if (payload.data.portnum === "TRACEROUTE_APP" || payload.data.portnum === "ROUTING_APP") {
        scheduleMeshRoutesRefresh();
        pulsePanel(mapPanel, "map");
      }
      if (
        payload.data.portnum === "TEXT_MESSAGE_APP"
        && payload.data.text_preview
        && payload.data.to_node_num === BROADCAST_NODE_NUM
      ) {
        pulsePanel(railToggleChat, "chat");
        pulsePanel(chatPanel, "chat");
      }
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

function initializeStaticUI() {
  renderPerspectiveLabel();
  renderConnectionIndicator();
  refreshKpiTicker();
  renderRouteToggle();
  updatePacketFilterButtons();
  updateNodeFilterButtons();
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

railToggleTraffic?.addEventListener("click", () => {
  setTrafficDrawerOpen(!state.trafficDrawerOpen);
});

/* Search toggle removed — search bar always visible (N-02) */

closeInspectorBtn?.addEventListener("click", () => {
  state.selectedNodeNum = null;
  renderNodeDetail(null);
  renderNodeList();
  renderMap(state.nodes);
  setInspectorOpen(false);
});

initializeStaticUI();

loadAll()
  .then((failures) => {
    startDecayRefreshLoop();
    connectEvents();
    reportLoadFailures(failures);
  })
  .catch(handleLoadError);
