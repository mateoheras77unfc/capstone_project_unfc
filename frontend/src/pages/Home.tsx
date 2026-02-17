import { Link } from "react-router-dom";
import {
  TrendingUp,
  BarChart3,
  BookOpen,
  Zap,
  Shield,
  GitBranch,
} from "lucide-react";
import agentAvatar from "@/assets/agent-avatar.png";

const navCards = [
  {
    path: "/forecasting",
    icon: TrendingUp,
    title: "Single Asset Forecasting",
    description:
      "Learn how models like LSTM and Prophet predict future prices using historical data.",
    accent: "primary",
  },
  {
    path: "/portfolio",
    icon: BarChart3,
    title: "Portfolio Optimization",
    description:
      "Understand how diversification and mean-variance optimization build better portfolios.",
    accent: "secondary",
  },
  {
    path: "/education",
    icon: BookOpen,
    title: "Educational Hub",
    description:
      "Guided tutorials, glossary, and quizzes to test your understanding.",
    accent: "accent",
  },
];

const concepts = [
  {
    icon: TrendingUp,
    title: "What is Forecasting?",
    text: "Using statistical models and machine learning to predict future asset prices based on historical patterns and trends.",
  },
  {
    icon: Zap,
    title: "What is Volatility?",
    text: "A measure of how much an asset's price fluctuates over time. Higher volatility means higher risk — and potentially higher reward.",
  },
  {
    icon: GitBranch,
    title: "Why Diversification Matters",
    text: "Holding assets that don't move together reduces overall portfolio risk without necessarily sacrificing returns.",
  },
];

const Index = () => {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="gradient-mesh absolute inset-0" />
        <div className="container relative py-20 sm:py-28">
          <div className="flex flex-col sm:flex-row items-center gap-10">
            <div className="shrink-0">
              <img
                src={agentAvatar}
                alt="Foxy teaching assistant"
                className="w-52 h-52 sm:w-72 sm:h-72 object-contain drop-shadow-[0_0_30px_hsl(191_100%_50%/0.35)]"
              />
            </div>
            <div className="text-center sm:text-left order-2 sm:order-1">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium mb-6">
                <Shield className="w-3.5 h-3.5" />
                Educational Platform
              </div>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight mb-6">
                Learn{" "}
                <span className="text-gradient-primary">
                  Investment Science
                </span>
                <br />
                With Real Data
              </h1>
              <p className="text-lg text-muted-foreground max-w-lg mb-10">
                Explore how forecasting models and portfolio optimization work
                using simulated market data. No prior finance experience needed.
              </p>
              <div className="flex items-center justify-center sm:justify-start gap-4">
                <Link
                  to="/forecasting"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
                >
                  <TrendingUp className="w-4 h-4" />
                  Start Exploring
                </Link>
                <Link
                  to="/education"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-border text-foreground font-medium hover:bg-muted/50 transition-colors"
                >
                  <BookOpen className="w-4 h-4" />
                  Learn First
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Teaching Agent */}
      <section className="container py-12">
        <div className="relative rounded-2xl border border-border bg-card/60 glass p-8 flex flex-col sm:flex-row items-center gap-6">
          <div className="shrink-0">
            <img
              src={agentAvatar}
              alt="InvestEd teaching assistant"
              className="w-32 h-32 sm:w-40 sm:h-40 object-contain drop-shadow-[0_0_20px_hsl(191_100%_50%/0.3)]"
            />
          </div>
          <div className="text-center sm:text-left">
            <p className="text-xs font-mono uppercase tracking-widest text-primary mb-1">
              Your Guide
            </p>
            <h2 className="text-xl font-bold mb-2">
              Hey! I'm <span className="text-gradient-primary">Foxy</span> 🦊
            </h2>
            <p className="text-muted-foreground leading-relaxed max-w-lg">
              I'll walk you through forecasting models, portfolio theory, and
              key investment concepts — step by step. No jargon, no pressure.
              Let's learn together!
            </p>
            <Link
              to="/education"
              className="inline-flex items-center gap-2 mt-4 px-5 py-2.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
            >
              <BookOpen className="w-4 h-4" />
              Start Learning with Foxy
            </Link>
          </div>
        </div>
      </section>

      {/* Navigation Cards */}
      <section className="container py-16">
        <div className="grid md:grid-cols-3 gap-6">
          {navCards.map((card) => (
            <Link
              key={card.path}
              to={card.path}
              className="group relative rounded-xl border border-border bg-card p-6 card-hover"
            >
              <div
                className={`w-12 h-12 rounded-lg flex items-center justify-center mb-4 ${
                  card.accent === "primary"
                    ? "bg-primary/10 text-primary"
                    : card.accent === "secondary"
                    ? "bg-secondary/10 text-secondary"
                    : "bg-accent/10 text-accent"
                }`}
              >
                <card.icon className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{card.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {card.description}
              </p>
              <div className="absolute bottom-6 right-6 text-muted-foreground/30 group-hover:text-primary/50 transition-colors">
                →
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Beginner Concepts */}
      <section className="container pb-20">
        <h2 className="text-2xl font-bold mb-2 text-center">Key Concepts</h2>
        <p className="text-muted-foreground text-center mb-10">
          Foundational ideas you'll explore throughout this platform
        </p>
        <div className="grid md:grid-cols-3 gap-6">
          {concepts.map((concept) => (
            <div
              key={concept.title}
              className="rounded-xl border border-border bg-card/50 p-6"
            >
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center mb-4">
                <concept.icon className="w-5 h-5 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2">{concept.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {concept.text}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Index;
