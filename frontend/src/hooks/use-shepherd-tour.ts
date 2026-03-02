"use client";

import { useEffect, useRef } from "react";

export interface TourStep {
  id: string;
  title: string;
  text: string;
  attachTo?: { element: string; on: "top" | "bottom" | "left" | "right" | "auto" };
}

interface UseShepherdTourOptions {
  /** localStorage key used to remember "already seen" state */
  tourKey: string;
  steps: TourStep[];
  /** If true, tour starts automatically on first visit (saved in localStorage) */
  autoStart?: boolean;
}

export function useShepherdTour({ tourKey, steps, autoStart = false }: UseShepherdTourOptions) {
  const tourRef = useRef<any>(null);

  useEffect(() => {
    // Dynamically import shepherd.js so it is never run on the server
    let cancelled = false;

    import("shepherd.js").then(({ default: Shepherd }) => {
      if (cancelled) return;

      const tour = new Shepherd.Tour({
        useModalOverlay: true,
        defaultStepOptions: {
          cancelIcon: { enabled: true },
          scrollTo: { behavior: "smooth", block: "center" },
          classes: "shepherd-theme-investanalytics",
        },
      });

      const totalSteps = steps.length;

      steps.forEach((step, index) => {
        const isLast = index === totalSteps - 1;
        const isFirst = index === 0;

        tour.addStep({
          id: step.id,
          title: step.title,
          text: `
            <div class="shepherd-progress-bar">
              <div class="shepherd-progress-fill" style="width:${((index + 1) / totalSteps) * 100}%"></div>
            </div>
            <p>${step.text}</p>
          `,
          attachTo: step.attachTo,
          buttons: [
            ...(!isFirst
              ? [{ label: "← Back", action: () => tour.back(), classes: "shepherd-btn-secondary" }]
              : []),
            { label: isLast ? "Finish ✓" : "Next →", action: () => (isLast ? tour.complete() : tour.next()), classes: "shepherd-btn-primary" },
          ],
          when: {
            show() {
              // Mark as seen on first step shown
              if (index === 0) {
                localStorage.setItem(tourKey, "seen");
              }
            },
          },
        });
      });

      tourRef.current = tour;

      // Auto-start if never seen before
      if (autoStart && !localStorage.getItem(tourKey)) {
        // Small delay so the DOM is fully rendered
        setTimeout(() => {
          if (!cancelled) tour.start();
        }, 600);
      }
    });

    return () => {
      cancelled = true;
      tourRef.current?.cancel?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startTour = () => {
    const tour = tourRef.current;
    if (!tour) return;
    // Cancel any in-progress session before restarting from step 1
    try { tour.cancel(); } catch (_) { /* already idle */ }
    tour.start();
  };

  const resetTour = () => {
    localStorage.removeItem(tourKey);
  };

  return { startTour, resetTour };
}
