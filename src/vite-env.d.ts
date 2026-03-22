/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  /** Optional Mapbox public token for TheaterMap basemap (Vite client bundle). */
  readonly VITE_MAPBOX_TOKEN?: string;
  /** Optional Mapbox style URL, e.g. mapbox://styles/mapbox/dark-v11 */
  readonly VITE_MAPBOX_STYLE?: string;
}
