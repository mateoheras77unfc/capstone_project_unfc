import { api } from "@/lib/api";
import { PortfolioClientWrapper } from "./PortfolioClientWrapper";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  // Fetch all available assets for the dropdown
  const assets = await api.getAssets().catch(() => []);

  return <PortfolioClientWrapper assets={assets} />;
}
