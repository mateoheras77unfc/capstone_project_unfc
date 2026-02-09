import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";

type Option = {
  value: string;
  label: string;
};

type Props = {
  value: string;
  onChange: (v: string) => void;
  options: Option[];
  placeholder?: string;
};

export function Select({ value, onChange, options, placeholder }: Props) {
  return (
    <motion.div className="relative w-56" whileHover={{ scale: 1.02 }}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="
          appearance-none w-full px-4 py-3 rounded-xl
          bg-slate-900/60
          border border-slate-700
          text-white
          focus:outline-none focus:ring-2 focus:ring-cyan-400/40
        "
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-cyan-400 pointer-events-none" />
    </motion.div>
  );
}
