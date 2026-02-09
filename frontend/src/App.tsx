import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Home from "./pages/Home";
import SingleAsset from "./pages/SingleAsset";
import Comparison from "./pages/Comparison";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="w-full flex justify-start py-4 text-sm text-slate-400 px-4">
        <div className="flex items-center gap-6">
          <Link to="/" className="hover:text-white transition-colors">
            Home
          </Link>
          <span className="text-slate-600">|</span>
          <Link to="/single" className="text-white font-medium">
            Single Asset
          </Link>
          <span className="text-slate-600">|</span>
          <Link to="/compare" className="hover:text-white transition-colors">
            Compare
          </Link>
        </div>
      </nav>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/single" element={<SingleAsset />} />
        <Route path="/compare" element={<Comparison />} />
      </Routes>
    </BrowserRouter>
  );
}
