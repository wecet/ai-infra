export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers:
      options.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check your input and try again.`,
    );
  }
  return response.json();
}
export const colors = [
  "#b7ed80",
  "#8bc5ff",
  "#ffc27a",
  "#d4acff",
  "#ff91ad",
  "#69ddd0",
  "#ffe77c",
];
export const color = (id) => colors[(id - 1) % colors.length];
