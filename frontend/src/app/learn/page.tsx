import { BookOpen, TrendingUp, PieChart, LineChart } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

const topics = [
  {
    icon: TrendingUp,
    title: "Price Forecasting",
    description:
      "Understand how EWM, Prophet, and LSTM models predict future stock prices using historical patterns and statistical techniques.",
  },
  {
    icon: PieChart,
    title: "Portfolio Theory",
    description:
      "Learn Modern Portfolio Theory — how diversification reduces risk and how the efficient frontier helps you maximize returns.",
  },
  {
    icon: LineChart,
    title: "Risk Metrics",
    description:
      "Explore Sharpe Ratio, Max Drawdown, Volatility, Skewness, and Kurtosis — the key numbers every investor should understand.",
  },
  {
    icon: BookOpen,
    title: "Optimization Methods",
    description:
      "Discover how PyPortfolioOpt solves for the ideal portfolio weights using convex optimization under real-world constraints.",
  },
];

export default function LearnPage() {
  return (
    <div className="relative min-h-[80vh] py-12 space-y-12">
      {/* Header */}
      <div className="text-center space-y-4 max-w-2xl mx-auto">
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-1.5 text-sm font-medium text-cyan-400">
          <BookOpen className="h-4 w-4" />
          Learning Center
        </div>
        <h1 className="text-5xl font-extrabold tracking-tight text-white">
          Investment{" "}
          <span className="bg-gradient-to-r from-cyan-400 to-violet-500 bg-clip-text text-transparent">
            Concepts
          </span>
        </h1>
        <p className="text-xl text-gray-400">
          Master the fundamentals behind every tool in this platform. No prior finance experience needed.
        </p>
      </div>

      {/* Topic cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
        {topics.map(({ icon: Icon, title, description }) => (
          <Card
            key={title}
            className="border border-white/8 bg-white/3 backdrop-blur hover:border-cyan-400/30 transition-colors"
          >
            <CardHeader>
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-400/10 mb-4">
                <Icon className="h-6 w-6 text-cyan-400" />
              </div>
              <CardTitle className="text-xl text-white">{title}</CardTitle>
              <CardDescription className="text-gray-400 text-base leading-relaxed">
                {description}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      <p className="text-center text-gray-500 text-base">
        More guided lessons coming soon. Start exploring the tools to learn by doing!
      </p>
    </div>
  );
}
