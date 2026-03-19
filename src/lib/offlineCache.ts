/**
 * IndexedDB cache for offline capability.
 * Stores API responses by key with optional TTL so the app can show last-known data when offline.
 */

const DB_NAME = "dwr-offline-cache";
const DB_VERSION = 1;
const STORE_NAME = "responses";

export interface CachedEntry<T = unknown> {
  key: string;
  data: T;
  storedAt: number;
  expiresAt?: number;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = (e) => {
      const db = (e.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "key" });
      }
    };
  });
}

/** Get cached value by key. Returns null if missing or expired. */
export async function getCached<T = unknown>(key: string): Promise<T | null> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(key);
      req.onsuccess = () => {
        const entry = req.result as CachedEntry<T> | undefined;
        if (!entry) {
          resolve(null);
          return;
        }
        if (entry.expiresAt != null && Date.now() > entry.expiresAt) {
          resolve(null);
          return;
        }
        resolve(entry.data);
      };
      req.onerror = () => reject(req.error);
      tx.oncomplete = () => db.close();
    });
  } catch {
    return null;
  }
}

/** Store value with optional TTL in seconds. */
export async function setCached<T = unknown>(
  key: string,
  data: T,
  ttlSeconds?: number
): Promise<void> {
  try {
    const db = await openDB();
    const storedAt = Date.now();
    const expiresAt = ttlSeconds != null ? storedAt + ttlSeconds * 1000 : undefined;
    const entry: CachedEntry<T> = { key, data, storedAt, expiresAt };
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const req = tx.objectStore(STORE_NAME).put(entry);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
      tx.oncomplete = () => db.close();
    });
  } catch {
    // IndexedDB not available (private mode, etc.)
  }
}

/** Check if we are likely offline (no navigator.onLine or failed fetch). */
export function isOffline(): boolean {
  return typeof navigator !== "undefined" && !navigator.onLine;
}
