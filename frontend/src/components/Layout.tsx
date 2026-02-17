import { Link, useLocation, Outlet } from "react-router-dom";
import { Home, TrendingUp, BarChart3 } from "lucide-react";

const navItems = [
  { path: "/", label: "Home", icon: Home },
  { path: "/single", label: "Single Asset", icon: TrendingUp },
  { path: "/compare", label: "Compare", icon: BarChart3 },
];

const Layout = () => {
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      {/* Header */}
      <header className="border-b border-border/50 backdrop-blur-md bg-background/80 sticky top-0 z-50">
        <div className="container flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-primary" />
            </div>
            <span className="font-semibold text-lg tracking-tight">
              UNF Investor
            </span>
          </Link>

          <nav className="flex items-center gap-2">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Page Content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6 text-center text-sm text-muted-foreground">
        Educational project • Not financial advice
      </footer>
    </div>
  );
};

export default Layout;
