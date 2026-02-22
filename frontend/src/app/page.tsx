import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, BarChart3, PieChart } from "lucide-react";
import { MouseTrail } from "@/components/MouseTrail";

export default function Home() {
  return (
    <div className="relative flex flex-col min-h-[80vh] justify-center gap-10 py-8 overflow-hidden">
      <MouseTrail />

      {/* Animated background blobs */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        {/* Blue blob — top-left */}
        <div className="blob-1 absolute -top-32 -left-32 h-[520px] w-[520px] rounded-full bg-[#0487D9] opacity-[0.12] blur-[90px]" />
        {/* Orange blob — top-right */}
        <div className="blob-2 absolute -top-20 -right-40 h-[480px] w-[480px] rounded-full bg-[#F27405] opacity-[0.10] blur-[80px]" />
        {/* Red-orange blob — bottom-left */}
        <div className="blob-3 absolute bottom-0 left-1/4 h-[400px] w-[400px] rounded-full bg-[#F23005] opacity-[0.08] blur-[70px]" />
        {/* Dark red blob — bottom-right */}
        <div className="blob-4 absolute -bottom-24 -right-24 h-[360px] w-[360px] rounded-full bg-[#A60303] opacity-[0.09] blur-[75px]" />
      </div>
      {/* Hero: mascot left, text right */}
      <div className="flex flex-col md:flex-row items-center gap-10">
        <div className="shrink-0">
          <Image
            src="/agent-avatar.png"
            alt="InvestAnalytics Mascot"
            width={260}
            height={260}
            className="drop-shadow-2xl"
          />
        </div>
        <div className="space-y-5 text-left">
          <h1 className="text-5xl font-extrabold tracking-tight sm:text-6xl md:text-7xl text-primary">
            Investment Analytics
          </h1>
          <p className="text-2xl text-muted-foreground max-w-[42rem]">
            Analyze individual stocks with advanced forecasting models and build optimized portfolios using modern portfolio theory.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
        <Card className="flex flex-col justify-between border-2 hover:border-primary transition-colors">
          <CardHeader>
            <BarChart3 className="h-14 w-14 mb-4 text-primary" />
            <CardTitle className="text-3xl">Stock Viewer</CardTitle>
            <CardDescription className="text-lg">
              Search for any stock to view its price history and generate forecasts using EWM, Prophet, or LSTM models.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/stock" passHref>
              <Button className="w-full group text-lg py-6 bg-primary hover:bg-primary/90">
                Open Stock Viewer
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card className="flex flex-col justify-between border-2 hover:border-secondary transition-colors">
          <CardHeader>
            <PieChart className="h-14 w-14 mb-4 text-secondary" />
            <CardTitle className="text-3xl">Portfolio Builder</CardTitle>
            <CardDescription className="text-lg">
              Construct a multi-asset portfolio and run PyPortfolioOpt to find the optimal weights for your investment goals.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/portfolio" passHref>
              <Button className="w-full group text-lg py-6 bg-secondary hover:bg-secondary/90">
                Build Portfolio
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
