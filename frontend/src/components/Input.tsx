import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  icon?: LucideIcon;
  className?: string;
};

export function Input({
  value,
  onChange,
  placeholder,
  icon: Icon,
  className = "",
}: Props) {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.15 }}
      className={`relative ${className}`}
    >
      {Icon && (
        <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
      )}

      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`h-12 w-full rounded-xl bg-slate-900/80
          border border-slate-700 px-4
          ${Icon ? "pl-11" : ""}
          text-white placeholder-slate-400
          focus:outline-none focus:ring-2 focus:ring-cyan-400/40`}
      />
    </motion.div>
  );
}
