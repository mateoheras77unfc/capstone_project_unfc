import { useEffect, useState } from "react";
import { getAssets, getPrices } from "../api/client";

export default function Comparison() {
  const [assets, setAssets] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    getAssets().then(setAssets);
  }, []);

  const toggle = (symbol: string) => {
    setSelected((prev) =>
      prev.includes(symbol)
        ? prev.filter((s) => s !== symbol)
        : [...prev, symbol]
    );
  };

  useEffect(() => {
    Promise.all(selected.map(getPrices)).then((data) => {
      setRows(
        data.map((prices, i) => ({
          symbol: selected[i],
          latest: prices?.[0],
        }))
      );
    });
  }, [selected]);

  return (
    <div style={{ padding: 32 }}>
      <h2>Asset Comparison</h2>

      {assets.map((a) => (
        <label key={a.symbol}>
          <input type="checkbox" onChange={() => toggle(a.symbol)} />
          {a.symbol}
        </label>
      ))}

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Close</th>
            <th>Volume</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td>{r.symbol}</td>
              <td>{r.latest?.close_price}</td>
              <td>{r.latest?.volume}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
