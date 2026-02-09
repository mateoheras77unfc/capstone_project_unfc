export function DataPreview({ prices }: { prices: any[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold mb-2 text-slate-300">
        Raw Data Preview
      </h3>
      <pre className="bg-slate-800 rounded-lg p-3 text-xs max-h-40 overflow-auto">
        {JSON.stringify(prices.slice(0, 5), null, 2)}
      </pre>
    </div>
  );
}
