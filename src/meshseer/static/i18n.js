(function () {
  "use strict";

  const DEFAULT_LOCALE = "en";
  const LOCALE_STORAGE_KEY = "meshseer.ui.language";

  const SUPPORTED_LOCALES = Object.freeze({
    en: Object.freeze({ label: "English", htmlLang: "en", intlLocale: "en-US" }),
    es: Object.freeze({ label: "Español", htmlLang: "es", intlLocale: "es-ES" }),
  });

  const EN = Object.freeze({
    "document.title": "Meshseer | LongFast Mesh Console",

    "common.appName": "Meshseer",
    "common.broadcast": "Broadcast",
    "common.complete": "COMPLETE",
    "common.flat": "Flat",
    "common.historyFor": "{label} history",
    "common.local": "Local",
    "common.na": "n/a",
    "common.noBaseline": "No baseline",
    "common.node": "Node",
    "common.nodeTelemetry": "Node telemetry",
    "common.nodeWithNum": "Node {num}",
    "common.sample": "sample",
    "common.samples": "samples",
    "common.selected": "Selected",
    "common.total": "{count} total",
    "common.unknown": "Unknown",
    "common.waiting": "Waiting",
    "trend.flatVsPrior": "Flat vs prior {context}",
    "trend.valueVsPrior": "{detail} vs prior {context}",

    "status.initialAria": "Offline. Waiting for status.",
    "status.receiverLink": "Receiver link",
    "status.waitingForStatus": "Waiting for status.",
    "status.receiverPending": "Receiver pending",
    "status.receiver": "Receiver",
    "status.live": "Live",
    "status.stale": "Stale",
    "status.connecting": "Connecting",
    "status.reconnecting": "Reconnecting",
    "status.blocked": "Blocked",
    "status.offline": "Offline",
    "status.degraded": "Degraded",
    "status.lastUpdate": "Last update {time}",
    "status.noLiveUpdates": "No live updates yet",
    "status.lastPacket": "Last packet {time}",
    "status.noPacketsHeard": "No packets heard yet",
    "status.linkActiveStale": "Link active but no fresh observations. {packet}. {updated}.",
    "status.linkActive": "Receiver link active. {packet}. {updated}.",
    "status.linkUnavailable": "Receiver link unavailable. {packet}. {updated}.",
    "status.streamReconnecting": "Event stream reconnecting. {packet}. {updated}.",
    "status.streamOpening": "Opening event stream. {packet}. {updated}.",
    "status.streamBlocked": "Event stream blocked by server policy. {packet}. {updated}.",
    "status.streamError": "Stream error. {packet}. {updated}.",
    "status.waitingForReceiver": "Waiting for receiver status. {packet}. {updated}.",
    "status.unableToLoad": "Unable to load dashboard",
    "status.requestFailed": "Request failed: {status}",
    "status.detail.connectionLost": "connection lost",
    "status.detail.demoLoaded": "Demo dataset loaded for headless preview",
    "status.detail.missingRadio": "missing radio",

    "stats.meshStats": "Mesh stats",
    "stats.nodes": "Nodes",
    "stats.active": "Active",
    "stats.pktPerMinute": "Pkt/m",
    "stats.paths": "Paths",

    "actions.zoomToFit": "Zoom to fit",
    "actions.refresh": "Refresh",
    "actions.closePanel": "Close panel",
    "actions.closeInspector": "Close inspector",

    "nav.toggleNodeRoster": "Toggle node roster",
    "nav.toggleChatPanel": "Toggle chat panel",
    "nav.toggleSignalsPanel": "Toggle signals panel",
    "nav.toggleTrafficPanel": "Toggle traffic panel",
    "nav.toggleOptionsPanel": "Toggle options panel",
    "nav.nodes": "Nodes",
    "nav.chat": "Chat",
    "nav.signals": "Signals",
    "nav.traffic": "Traffic",
    "nav.options": "Options",

    "map.longFastNodeMap": "LongFast node map",
    "map.waitingForNodeLocations": "Waiting for LongFast node locations.",
    "map.noMappedNodes24h": "No mapped nodes heard in the last 24 hours.",
    "map.routesHidden": "Route overlays are hidden.",
    "map.noRouteOverlays": "No route overlays available for the current node set.",
    "map.lastHeard": "Last heard {time}",

    "routes.hide": "Hide Routes",
    "routes.show": "Show Routes",
    "routes.forward": "Forward",
    "routes.return": "Return",
    "routes.older": "Older",
    "routes.route": "Route",
    "routes.latestRoute": "Latest route",
    "routes.unavailable": "Route unavailable",

    "path.direct": "Direct",
    "path.directRf": "Direct RF",
    "path.forwardOnly": "Forward only",
    "path.mqtt": "MQTT",
    "path.oneHop": "1 Hop",
    "path.hops": "{count} Hops",
    "path.pathUnknown": "Path Unknown",
    "path.pattern": "Pattern",
    "path.receiver": "Receiver",
    "path.receiverLocal": "Receiver-local node",
    "path.relayed": "Relayed",
    "path.roundTrip": "Round trip",
    "path.throughMqtt": "Observed through an MQTT bridge",
    "path.noEstimate": "No passive path estimate yet",
    "path.directFromReceiver": "Direct RF path from this receiver",
    "path.hopsFromReceiver": "{count} hops away from this receiver",
    "path.via": "Via {label}",
    "path.viaMqtt": "Via MQTT",

    "nodes.panelCount": "{heard} heard · {active} active",
    "nodes.searchPlaceholder": "Filter by name or ID…",
    "nodes.filtersLabel": "Node filters",
    "nodes.filter.active": "Active",
    "nodes.filter.directRf": "Direct RF",
    "nodes.filter.mapped": "Mapped",
    "nodes.filter.mqtt": "MQTT",
    "nodes.filter.stale": "Stale",
    "nodes.noNodeSelectedTitle": "No Node Selected",
    "nodes.noNodeSelectedBody": "Select a node from the map or roster when positions arrive.",
    "nodes.noMatchingTitle": "No Matching Nodes",
    "nodes.noMatchingBody": "Adjust the roster filters or search query to widen the view.",
    "nodes.noNodesTitle": "No Nodes Yet",
    "nodes.noNodesBody": "LongFast nodes appear here as the receiver hears them.",
    "nodes.nodeDetail": "Node Detail",
    "nodes.selectedNode": "Selected Node",
    "nodes.freshness.live": "LIVE",
    "nodes.freshness.recent": "RECENT",
    "nodes.freshness.stale": "STALE",
    "nodes.freshness.seen": "SEEN",
    "nodes.metric.path": "Path",
    "nodes.metric.hopsAway": "Hops Away",
    "nodes.metric.lastHeard": "Last Heard",
    "nodes.metric.first": "First {time}",
    "nodes.metric.packetsHeard": "Packets Heard",
    "nodes.metric.battery": "Battery",
    "nodes.snrHistory": "Node SNR history",
    "nodes.utilHistory": "Node channel utilization and air utilization history",
    "nodes.snrDetail": "Min {min} · Max {max} · Avg {avg}",
    "nodes.utilLabel": "CH util / Air util TX",
    "nodes.utilValues": "CH {ch} · TX {tx}",
    "nodes.samples": "Samples {count}",
    "nodes.packetBreakdown": "Packet breakdown",
    "nodes.broadcastCount": "Broadcast {count}",
    "nodes.recentPackets": "Recent packets",
    "nodes.recentPacketsUnavailable": "Recent packets are unavailable right now.",
    "nodes.loadingRecentPackets": "Loading recent packets…",
    "nodes.noRecentPackets": "No recent packets from this node yet.",
    "nodes.toDestination": "To {destination}",

    "options.theme": "Theme",
    "options.language": "Language",
    "options.language.english": "English",
    "options.language.spanish": "Español",
    "options.theme.classic": "Classic (light)",
    "options.theme.classicDark": "Classic (dark)",
    "options.theme.amberMonochrome": "Amber Monochrome",

    "traffic.recentPackets": "Recent Packets",
    "traffic.show": "Show",
    "traffic.recentPacketCount": "Recent packet count",
    "traffic.packetFilters": "Packet filters",
    "traffic.filter.all": "All",
    "traffic.filter.text": "Text",
    "traffic.filter.position": "Position",
    "traffic.filter.telemetry": "Telemetry",
    "traffic.filter.other": "Other",
    "traffic.exportVisibleCsv": "Export visible packets as CSV",
    "traffic.exportVisibleCountCsv": "Export {count} visible packets as CSV",
    "traffic.noVisiblePacketsToExport": "No visible packets to export",
    "traffic.noPacketsMatch": "No packets match the current filter.",
    "traffic.when": "When",
    "traffic.from": "From",
    "traffic.to": "To",
    "traffic.port": "Port",
    "traffic.deliveredBy": "Delivered By",
    "traffic.snr": "SNR",
    "traffic.path": "Path",
    "traffic.port.text": "Text",
    "traffic.port.positionShort": "Pos",
    "traffic.port.telemetryShort": "Telem",
    "traffic.port.admin": "Admin",
    "traffic.port.other": "Other",

    "chat.emptyTitle": "No Chat Yet",
    "chat.emptyBody": "Broadcast LongFast messages will stream here when heard by this receiver.",

    "signals.waitingIntel": "Waiting for passive mesh traffic to build an intel view.",
    "signals.noPassiveTraffic": "No passive traffic yet.",
    "signals.heardNodes": "Heard nodes",
    "signals.heardNodesHistory": "Heard nodes history",
    "signals.coverage": "Coverage",
    "signals.coverageHistory": "Coverage history",
    "signals.coverageDetail": "{mapped} of {total}",
    "signals.noNodeRoster": "No node roster yet",
    "signals.channelUtilization": "Channel utilization",
    "signals.chUtil": "Ch. util",
    "signals.airUtilTx": "Air util TX",
    "signals.peakSamples": "Peak {peak} · {count} {sampleLabel}",
    "signals.receiverIdentityWaiting": "Waiting for receiver identity",
    "signals.telemetryPending": "Telemetry pending",
    "signals.routingHealth": "Routing health",
    "signals.dominantPath": "Dominant path",
    "signals.dominantPathAria": "What is dominant path?",
    "signals.dominantPathHelp": "Which routing mode — Direct RF, Relayed, MQTT, or Unknown — carries the largest share of recent packets.",
    "signals.directRfPackets": "{percent}% · {count} pkts",
    "signals.noDirectTraffic": "No direct traffic",
    "signals.totalPackets": "Total packets",
    "signals.packetBreakdown": "Packet breakdown",
    "signals.packetType.text": "Text",
    "signals.packetType.telemetry": "Telemetry",
    "signals.packetType.position": "Position",
    "signals.packetType.other": "Other",
    "signals.path.noFreshRead": "No fresh path read",
    "signals.path.mqttHeavy": "MQTT-heavy",
    "signals.path.relayHeavy": "Relay heavy",
    "signals.path.mostlyDirect": "Mostly direct",
    "signals.path.mixed": "Mixed paths",

    "traceroute.title": "Traceroute",
    "traceroute.noAttempts": "No traceroute attempts recorded for this node yet.",
    "traceroute.success": "Success",
    "traceroute.ackOnly": "Ack only",
    "traceroute.timeout": "Timeout",
    "traceroute.error": "Error",
    "traceroute.completePath": "Complete path captured",
    "traceroute.seen": "Seen",
    "traceroute.hops": "Hops",
    "traceroute.request": "Request",
    "traceroute.trace": "Trace",

    "relative.justNow": "Just now",
    "relative.minutesAgo": "{count}m ago",
    "relative.hoursAgo": "{count}h ago",
    "relative.daysAgo": "{count}d ago",
  });

  const ES = Object.freeze({
    "document.title": "Meshseer | Consola LongFast Mesh",

    "common.appName": "Meshseer",
    "common.broadcast": "Broadcast",
    "common.complete": "COMPLETO",
    "common.flat": "Estable",
    "common.historyFor": "Historial de {label}",
    "common.local": "Local",
    "common.na": "n/d",
    "common.noBaseline": "Sin base",
    "common.node": "Nodo",
    "common.nodeTelemetry": "Telemetría nodo",
    "common.nodeWithNum": "Nodo {num}",
    "common.sample": "muestra",
    "common.samples": "muestras",
    "common.selected": "Seleccionado",
    "common.total": "{count} total",
    "common.unknown": "Desconocido",
    "common.waiting": "Esperando",
    "trend.flatVsPrior": "Estable vs previo {context}",
    "trend.valueVsPrior": "{detail} vs previo {context}",

    "status.initialAria": "Offline. Esperando estado.",
    "status.receiverLink": "Enlace receptor",
    "status.waitingForStatus": "Esperando estado.",
    "status.receiverPending": "Receptor pendiente",
    "status.receiver": "Receptor",
    "status.live": "En vivo",
    "status.stale": "Viejo",
    "status.connecting": "Conectando",
    "status.reconnecting": "Reconectando",
    "status.blocked": "Bloqueado",
    "status.offline": "Offline",
    "status.degraded": "Degradado",
    "status.lastUpdate": "Últ. act. {time}",
    "status.noLiveUpdates": "Sin updates en vivo",
    "status.lastPacket": "Últ. paquete {time}",
    "status.noPacketsHeard": "Sin paquetes aún",
    "status.linkActiveStale": "Enlace activo sin datos frescos. {packet}. {updated}.",
    "status.linkActive": "Enlace receptor activo. {packet}. {updated}.",
    "status.linkUnavailable": "Enlace receptor no disponible. {packet}. {updated}.",
    "status.streamReconnecting": "Stream de eventos reconectando. {packet}. {updated}.",
    "status.streamOpening": "Abriendo stream de eventos. {packet}. {updated}.",
    "status.streamBlocked": "Stream bloqueado por política del servidor. {packet}. {updated}.",
    "status.streamError": "Error de stream. {packet}. {updated}.",
    "status.waitingForReceiver": "Esperando estado del receptor. {packet}. {updated}.",
    "status.unableToLoad": "No se pudo cargar el panel",
    "status.requestFailed": "Falló la petición: {status}",
    "status.detail.connectionLost": "conexión perdida",
    "status.detail.demoLoaded": "Dataset demo cargado para preview headless",
    "status.detail.missingRadio": "radio no encontrada",

    "stats.meshStats": "Stats mesh",
    "stats.nodes": "Nodos",
    "stats.active": "Activos",
    "stats.pktPerMinute": "Pkt/m",
    "stats.paths": "Rutas",

    "actions.zoomToFit": "Ajustar zoom",
    "actions.refresh": "Actualizar",
    "actions.closePanel": "Cerrar panel",
    "actions.closeInspector": "Cerrar inspector",

    "nav.toggleNodeRoster": "Alternar lista de nodos",
    "nav.toggleChatPanel": "Alternar panel de chat",
    "nav.toggleSignalsPanel": "Alternar panel de señales",
    "nav.toggleTrafficPanel": "Alternar panel de tráfico",
    "nav.toggleOptionsPanel": "Alternar panel de opciones",
    "nav.nodes": "Nodos",
    "nav.chat": "Chat",
    "nav.signals": "Señales",
    "nav.traffic": "Tráfico",
    "nav.options": "Opciones",

    "map.longFastNodeMap": "Mapa de nodos LongFast",
    "map.waitingForNodeLocations": "Esperando ubicaciones LongFast.",
    "map.noMappedNodes24h": "Sin nodos mapeados en las últimas 24 h.",
    "map.routesHidden": "Las rutas están ocultas.",
    "map.noRouteOverlays": "No hay rutas para el conjunto actual de nodos.",
    "map.lastHeard": "Últ. oído {time}",

    "routes.hide": "Ocultar rutas",
    "routes.show": "Mostrar rutas",
    "routes.forward": "Ida",
    "routes.return": "Vuelta",
    "routes.older": "Viejas",
    "routes.route": "Ruta",
    "routes.latestRoute": "Última ruta",
    "routes.unavailable": "Ruta no disponible",

    "path.direct": "Directo",
    "path.directRf": "Direct RF",
    "path.forwardOnly": "Solo ida",
    "path.mqtt": "MQTT",
    "path.oneHop": "1 salto",
    "path.hops": "{count} saltos",
    "path.pathUnknown": "Ruta desconocida",
    "path.pattern": "Patrón",
    "path.receiver": "Receptor",
    "path.receiverLocal": "Nodo local del receptor",
    "path.relayed": "Repetido",
    "path.roundTrip": "Ida y vuelta",
    "path.throughMqtt": "Observado por un puente MQTT",
    "path.noEstimate": "Sin estimación pasiva aún",
    "path.directFromReceiver": "Ruta Direct RF desde este receptor",
    "path.hopsFromReceiver": "{count} saltos desde este receptor",
    "path.via": "Vía {label}",
    "path.viaMqtt": "Vía MQTT",

    "nodes.panelCount": "{heard} oídos · {active} activos",
    "nodes.searchPlaceholder": "Filtrar nombre o ID…",
    "nodes.filtersLabel": "Filtros de nodos",
    "nodes.filter.active": "Activos",
    "nodes.filter.directRf": "Direct RF",
    "nodes.filter.mapped": "Mapeados",
    "nodes.filter.mqtt": "MQTT",
    "nodes.filter.stale": "Viejos",
    "nodes.noNodeSelectedTitle": "Sin nodo seleccionado",
    "nodes.noNodeSelectedBody": "Selecciona un nodo del mapa o lista cuando lleguen posiciones.",
    "nodes.noMatchingTitle": "Sin nodos coincidentes",
    "nodes.noMatchingBody": "Ajusta filtros o búsqueda para ampliar la vista.",
    "nodes.noNodesTitle": "Sin nodos aún",
    "nodes.noNodesBody": "Los nodos LongFast aparecen aquí cuando el receptor los oye.",
    "nodes.nodeDetail": "Detalle nodo",
    "nodes.selectedNode": "Nodo seleccionado",
    "nodes.freshness.live": "ACTIVO",
    "nodes.freshness.recent": "RECIENTE",
    "nodes.freshness.stale": "VIEJO",
    "nodes.freshness.seen": "VISTO",
    "nodes.metric.path": "Ruta",
    "nodes.metric.hopsAway": "Saltos",
    "nodes.metric.lastHeard": "Últ. oído",
    "nodes.metric.first": "Primero {time}",
    "nodes.metric.packetsHeard": "Paquetes oídos",
    "nodes.metric.battery": "Batería",
    "nodes.snrHistory": "Historial SNR del nodo",
    "nodes.utilHistory": "Historial de utilización de canal y aire del nodo",
    "nodes.snrDetail": "Min {min} · Max {max} · Prom {avg}",
    "nodes.utilLabel": "CH util / Air util TX",
    "nodes.utilValues": "CH {ch} · TX {tx}",
    "nodes.samples": "Muestras {count}",
    "nodes.packetBreakdown": "Desglose paquetes",
    "nodes.broadcastCount": "Broadcast {count}",
    "nodes.recentPackets": "Paquetes recientes",
    "nodes.recentPacketsUnavailable": "Paquetes recientes no disponibles ahora.",
    "nodes.loadingRecentPackets": "Cargando paquetes recientes…",
    "nodes.noRecentPackets": "Sin paquetes recientes de este nodo aún.",
    "nodes.toDestination": "A {destination}",

    "options.theme": "Tema",
    "options.language": "Idioma",
    "options.language.english": "English",
    "options.language.spanish": "Español",
    "options.theme.classic": "Clásico (claro)",
    "options.theme.classicDark": "Clásico (oscuro)",
    "options.theme.amberMonochrome": "Ámbar Monocromo",

    "traffic.recentPackets": "Paquetes recientes",
    "traffic.show": "Ver",
    "traffic.recentPacketCount": "Cantidad de paquetes recientes",
    "traffic.packetFilters": "Filtros de paquetes",
    "traffic.filter.all": "Todos",
    "traffic.filter.text": "Texto",
    "traffic.filter.position": "Posición",
    "traffic.filter.telemetry": "Telemetría",
    "traffic.filter.other": "Otros",
    "traffic.exportVisibleCsv": "Exportar paquetes visibles como CSV",
    "traffic.exportVisibleCountCsv": "Exportar {count} paquetes visibles como CSV",
    "traffic.noVisiblePacketsToExport": "Sin paquetes visibles para exportar",
    "traffic.noPacketsMatch": "Ningún paquete coincide con el filtro.",
    "traffic.when": "Cuándo",
    "traffic.from": "De",
    "traffic.to": "A",
    "traffic.port": "Port",
    "traffic.deliveredBy": "Entregado por",
    "traffic.snr": "SNR",
    "traffic.path": "Ruta",
    "traffic.port.text": "Texto",
    "traffic.port.positionShort": "Pos",
    "traffic.port.telemetryShort": "Telem",
    "traffic.port.admin": "Admin",
    "traffic.port.other": "Otro",

    "chat.emptyTitle": "Sin chat aún",
    "chat.emptyBody": "Los mensajes Broadcast LongFast aparecerán aquí cuando este receptor los oiga.",

    "signals.waitingIntel": "Esperando tráfico mesh pasivo para crear la vista intel.",
    "signals.noPassiveTraffic": "Sin tráfico pasivo aún.",
    "signals.heardNodes": "Nodos oídos",
    "signals.heardNodesHistory": "Historial de nodos oídos",
    "signals.coverage": "Cobertura",
    "signals.coverageHistory": "Historial de cobertura",
    "signals.coverageDetail": "{mapped} de {total}",
    "signals.noNodeRoster": "Sin lista de nodos aún",
    "signals.channelUtilization": "Utilización de canal",
    "signals.chUtil": "Ch. util",
    "signals.airUtilTx": "Air util TX",
    "signals.peakSamples": "Pico {peak} · {count} {sampleLabel}",
    "signals.receiverIdentityWaiting": "Esperando identidad del receptor",
    "signals.telemetryPending": "Telemetría pendiente",
    "signals.routingHealth": "Salud de rutas",
    "signals.dominantPath": "Ruta dominante",
    "signals.dominantPathAria": "¿Qué es ruta dominante?",
    "signals.dominantPathHelp": "Qué modo de ruta — Direct RF, Repetido, MQTT o Desconocido — transporta más paquetes recientes.",
    "signals.directRfPackets": "{percent}% · {count} pkts",
    "signals.noDirectTraffic": "Sin tráfico directo",
    "signals.totalPackets": "Paquetes totales",
    "signals.packetBreakdown": "Desglose paquetes",
    "signals.packetType.text": "Texto",
    "signals.packetType.telemetry": "Telemetría",
    "signals.packetType.position": "Posición",
    "signals.packetType.other": "Otros",
    "signals.path.noFreshRead": "Sin lectura de ruta fresca",
    "signals.path.mqttHeavy": "Mucho MQTT",
    "signals.path.relayHeavy": "Mucho relay",
    "signals.path.mostlyDirect": "Mayormente directo",
    "signals.path.mixed": "Rutas mixtas",

    "traceroute.title": "Traceroute",
    "traceroute.noAttempts": "Sin intentos de traceroute para este nodo aún.",
    "traceroute.success": "Éxito",
    "traceroute.ackOnly": "Solo ACK",
    "traceroute.timeout": "Timeout",
    "traceroute.error": "Error",
    "traceroute.completePath": "Ruta completa capturada",
    "traceroute.seen": "Visto",
    "traceroute.hops": "Saltos",
    "traceroute.request": "Pedido",
    "traceroute.trace": "Trace",

    "relative.justNow": "Ahora",
    "relative.minutesAgo": "hace {count}m",
    "relative.hoursAgo": "hace {count}h",
    "relative.daysAgo": "hace {count}d",
  });

  const TRANSLATIONS = Object.freeze({
    en: EN,
    es: ES,
  });

  function normalizeLocale(value) {
    if (typeof value !== "string") {
      return null;
    }
    const normalized = value.trim().toLowerCase().replace("_", "-").split("-", 1)[0];
    return Object.prototype.hasOwnProperty.call(SUPPORTED_LOCALES, normalized) ? normalized : null;
  }

  function readStoredLocale() {
    try {
      const savedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
      const normalizedLocale = normalizeLocale(savedLocale);
      if (savedLocale != null && normalizedLocale == null) {
        window.localStorage.removeItem(LOCALE_STORAGE_KEY);
      }
      return normalizedLocale;
    } catch (_error) {
      return null;
    }
  }

  function browserLocale() {
    const candidates = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    for (const candidate of candidates) {
      const normalized = normalizeLocale(candidate);
      if (normalized) {
        return normalized;
      }
    }
    return DEFAULT_LOCALE;
  }

  let currentLocale = readStoredLocale() || browserLocale();

  function interpolate(template, params = {}) {
    return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => (
      Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match
    ));
  }

  function t(key, params = {}) {
    const catalog = TRANSLATIONS[currentLocale] || TRANSLATIONS[DEFAULT_LOCALE];
    const template = catalog[key] ?? TRANSLATIONS[DEFAULT_LOCALE][key] ?? key;
    return interpolate(template, params);
  }

  function writeStoredLocale(locale) {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch (_error) {
      return false;
    }
    return true;
  }

  function applyDocumentLanguage() {
    const meta = SUPPORTED_LOCALES[currentLocale] || SUPPORTED_LOCALES[DEFAULT_LOCALE];
    document.documentElement.lang = meta.htmlLang;
    document.title = t("document.title");
  }

  function setText(element, key) {
    if (!element || !key) {
      return;
    }
    element.textContent = t(key);
  }

  function setAttribute(element, attributeName, key) {
    if (!element || !attributeName || !key) {
      return;
    }
    element.setAttribute(attributeName, t(key));
  }

  function applyStaticTranslations(root = document) {
    applyDocumentLanguage();
    root.querySelectorAll("[data-i18n]").forEach((element) => {
      setText(element, element.dataset.i18n);
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      setAttribute(element, "aria-label", element.dataset.i18nAriaLabel);
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      setAttribute(element, "placeholder", element.dataset.i18nPlaceholder);
    });
    root.querySelectorAll("[data-i18n-title]").forEach((element) => {
      setAttribute(element, "title", element.dataset.i18nTitle);
    });
  }

  function setLocale(locale, { persist = false } = {}) {
    const normalized = normalizeLocale(locale) || DEFAULT_LOCALE;
    currentLocale = normalized;
    if (persist) {
      writeStoredLocale(normalized);
    }
    applyStaticTranslations();
    return currentLocale;
  }

  applyDocumentLanguage();

  window.MeshseerI18n = Object.freeze({
    DEFAULT_LOCALE,
    LOCALE_STORAGE_KEY,
    SUPPORTED_LOCALES,
    translations: TRANSLATIONS,
    applyStaticTranslations,
    intlLocale: () => (SUPPORTED_LOCALES[currentLocale] || SUPPORTED_LOCALES[DEFAULT_LOCALE]).intlLocale,
    locale: () => currentLocale,
    normalizeLocale,
    setLocale,
    t,
  });
}());
