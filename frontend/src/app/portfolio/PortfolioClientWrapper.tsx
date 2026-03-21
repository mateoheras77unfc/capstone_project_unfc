"use client";

import nextDynamic from "next/dynamic";
import type { AssetOut } from "@/types/api";

const PortfolioBuilder = nextDynamic(
  () => import("./PortfolioBuilder").then((m) => m.PortfolioBuilder),
  { ssr: false }
);

export function PortfolioClientWrapper({ assets }: { assets: AssetOut[] }) {
  return <PortfolioBuilder assets={assets} />;
}
