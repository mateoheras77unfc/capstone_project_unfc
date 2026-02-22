"use client";

import { useEffect, useState } from "react";

export function LocalEnvBanner() {
  const [isLocal, setIsLocal] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      setIsLocal(true);
    }
  }, []);

  if (!isLocal) return null;

  return (
    <div className="bg-yellow-400 text-yellow-900 px-4 py-2 text-sm font-medium text-center flex items-center justify-center gap-2 z-50 relative">
      <span className="flex h-2 w-2 rounded-full bg-yellow-600 animate-pulse"></span>
      <strong>Local Environment</strong>
      <span className="opacity-75 mx-2">|</span>
      <span>Studio: http://localhost:54323</span>
      <span className="opacity-75 mx-2">|</span>
      <span>API: http://127.0.0.1:8000</span>
    </div>
  );
}
