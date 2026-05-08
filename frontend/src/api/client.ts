import axios from "axios";

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : undefined;
}

export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: { "X-Requested-With": "XMLHttpRequest" },
});

apiClient.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  if (method && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const token = readCookie("csrftoken");
    if (token) {
      config.headers = config.headers ?? {};
      config.headers["X-CSRFToken"] = token;
    }
  }
  return config;
});
