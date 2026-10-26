const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

let isHandlingUnauthorized = false;

export function handleUnauthorizedSession() {
  logout();

  if (typeof window !== "undefined") {
    if (!isHandlingUnauthorized) {
      isHandlingUnauthorized = true;
      window.dispatchEvent(new Event("campusguard_auth_expired"));
      setTimeout(() => {
        isHandlingUnauthorized = false;
      }, 1000);
    }
  }
}

export async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem("campusguard_token");

  const headers = {
    ...options.headers,
  };

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    if (response.status === 401 && endpoint !== "/login") {
      handleUnauthorizedSession();
    }

    let errorMessage = "Request failed";
    if (typeof data.detail === "string") {
      errorMessage = data.detail;
    } else if (Array.isArray(data.detail) && data.detail.length > 0) {
      errorMessage = data.detail
        .map((item) => (typeof item === "object" ? item.msg || JSON.stringify(item) : String(item)))
        .join("; ");
    } else if (data.message) {
      errorMessage = data.message;
    }

    throw new Error(errorMessage);
  }

  return data;
}

export async function login(email, password) {
  const response = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || "Login failed"
    );
  }

  try {
    localStorage.setItem(
      "campusguard_token",
      data.access_token
    );

    localStorage.setItem(
      "campusguard_user",
      JSON.stringify({
        user_id: data.user_id,
        name: data.name,
        email: data.email,
        role: data.role,
      })
    );
  } catch {
    // ignore storage access errors
  }

  return data;
}

export function logout() {
  try {
    localStorage.removeItem("campusguard_token");
    localStorage.removeItem("campusguard_user");
  } catch {
    // ignore storage access errors
  }
}

export async function fetchAttachmentBlob(endpoint) {
  if (!endpoint || typeof endpoint !== "string") {
    throw new Error("Invalid attachment endpoint");
  }

  const resolvedUrl = new URL(endpoint, API_URL);
  const apiOrigin = new URL(API_URL).origin;

  if (resolvedUrl.origin !== apiOrigin || !resolvedUrl.pathname.startsWith("/uploads/")) {
    throw new Error("Untrusted attachment URL or invalid pathname");
  }

  const token = localStorage.getItem("campusguard_token");
  const headers = {};

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(resolvedUrl.toString(), { headers });

  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorizedSession();
    }
    throw new Error(`Failed to load attachment (${response.status})`);
  }

  return await response.blob();
}

export { API_URL };