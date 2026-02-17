import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import SingleAsset from "./pages/SingleAsset";
import Comparison from "./pages/Comparison";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/single" element={<SingleAsset />} />
          <Route path="/compare" element={<Comparison />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
