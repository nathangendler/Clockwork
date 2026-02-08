export const API_BASE =
  import.meta.env.VITE_API_BASE || "http://127.0.0.1:8080";

// Detect if running as Chrome extension
const isExtension = typeof chrome !== 'undefined' && chrome.storage && chrome.identity;

// Get session token from Chrome storage (returns a Promise)
function getSessionToken() {
  if (!isExtension) return Promise.resolve(null);
  return new Promise((resolve) => {
    chrome.storage.local.get(['sessionToken'], (result) => {
      resolve(result.sessionToken || null);
    });
  });
}

export async function api(path, opts = {}) {
  const headers = { ...opts.headers };

  if (isExtension) {
    // Chrome extension mode - use Authorization header
    const token = await getSessionToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(`${API_BASE}${path}`, {
      ...opts,
      headers,
    });
  } else {
    // Browser dev mode - use cookies
    return fetch(`${API_BASE}${path}`, {
      ...opts,
      credentials: "include",
      headers,
    });
  }
}
