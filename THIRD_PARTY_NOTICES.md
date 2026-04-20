# Third-Party Notices

Meshseer itself is licensed under `GPL-3.0-only`. The vendored assets listed below keep their own upstream licenses.

Meshseer redistributes a small set of vendored frontend assets so the UI can run without pulling those files from a third-party CDN at runtime.

## Vendored Assets

### Leaflet

- Purpose: interactive map JavaScript, CSS, and marker images
- Vendored path: `src/meshseer/static/vendor/leaflet/`
- Upstream project: <https://github.com/Leaflet/Leaflet>
- Upstream website: <https://leafletjs.com/>
- License: BSD-2-Clause
- Included license text: `src/meshseer/static/vendor/leaflet/LICENSE`

### IBM Plex Mono

- Purpose: UI monospace font files (`400`, `500`, `600`)
- Vendored path: `src/meshseer/static/vendor/fonts/`
- Upstream project: <https://github.com/IBM/plex>
- License: SIL Open Font License 1.1
- Included license text: `src/meshseer/static/vendor/fonts/LICENSE.ibm-plex-mono.txt`

### Space Grotesk

- Purpose: UI display/text font files (`400`, `500`, `700`)
- Vendored path: `src/meshseer/static/vendor/fonts/`
- Upstream project: <https://github.com/floriankarsten/space-grotesk>
- License: SIL Open Font License 1.1
- Included license text: `src/meshseer/static/vendor/fonts/LICENSE.space-grotesk.txt`

## Runtime Service Attribution

Meshseer does not vendor or redistribute the map tile service. The default map background is requested at runtime from CARTO raster basemaps with OpenStreetMap attribution. The browser map displays attribution for that service during normal use.

If you redistribute Meshseer with a different basemap provider, review that provider's terms and attribution requirements before shipping it.
