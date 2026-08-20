/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute origin of the deployed API, e.g. https://api.example.com.
   *  Leave unset for local development, where the Vite proxy handles /api. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
