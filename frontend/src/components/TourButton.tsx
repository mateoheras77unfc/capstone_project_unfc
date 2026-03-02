"use client";

import { BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useShepherdTour, TourStep } from "@/hooks/use-shepherd-tour";

interface TourButtonProps {
  tourKey: string;
  steps: TourStep[];
}

/**
 * A labeled "Take a Tour" button that starts a Shepherd.js guided tour.
 * Auto-starts on first visit; clicking always restarts from step 1.
 */
export function TourButton({ tourKey, steps }: TourButtonProps) {
  const { startTour } = useShepherdTour({ tourKey, steps, autoStart: true });

  return (
    <Button
      variant="outline"
      onClick={startTour}
      aria-label="Open guided tour"
      className="flex items-center gap-2 h-10 px-4 border-cyan-400/40 text-cyan-400 hover:bg-cyan-400/10 hover:border-cyan-400 hover:text-cyan-300 transition-all font-medium"
    >
      <BookOpen className="h-4 w-4 shrink-0" />
      Take a Tour
    </Button>
  );
}
