import { useEffect } from "react";

export function imagePoint(event, rect, image) {
  return { x: Math.max(0, Math.min(image.width, (event.clientX - rect.left) / (rect.width || 1) * image.width)),
    y: Math.max(0, Math.min(image.height, (event.clientY - rect.top) / (rect.height || 1) * image.height)) };
}

export function useUnsavedGuard(blocked) {
  useEffect(() => {
    function prevent(event) { if (blocked) { event.preventDefault(); event.returnValue = ""; } }
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [blocked]);
}
