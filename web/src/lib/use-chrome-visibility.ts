"use client";
/* Sticky chrome (header, tabs, filters) that gets out of the way while you
   scroll down and comes back the moment you pause or nudge upwards. */
import { useEffect, useState } from "react";

export function useChromeHidden(topThreshold = 120) {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let lastY = window.scrollY;
    let idle: ReturnType<typeof setTimeout> | undefined;
    let frame = 0;

    const evaluate = () => {
      const y = window.scrollY;
      const dy = y - lastY;
      if (y < topThreshold) setHidden(false);          // near the top: always visible
      else if (dy > 8) setHidden(true);                // scrolling down: get out of the way
      else if (dy < -8) setHidden(false);              // nudged up: come back
      lastY = y;
      clearTimeout(idle);
      idle = setTimeout(() => setHidden(false), 350);  // stopped scrolling: come back
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; evaluate(); });
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      clearTimeout(idle);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [topThreshold]);

  return hidden;
}
