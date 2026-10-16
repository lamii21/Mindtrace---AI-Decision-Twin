import { useEffect, useState } from "react";

/** Used to simplify the 3D scene (lower DPR, fewer particles) on small viewports. */
export function useIsMobile(breakpointPx = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${breakpointPx}px)`);
    setIsMobile(query.matches);
    const listener = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, [breakpointPx]);

  return isMobile;
}
