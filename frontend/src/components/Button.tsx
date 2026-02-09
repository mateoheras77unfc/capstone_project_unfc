import { RefreshCw } from "lucide-react";

type Props = {
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  children: string;
};

export function Button({ onClick, disabled, loading, children }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="btn-primary flex items-center gap-3 px-6"
    >
      <RefreshCw className={`w-5 h-5 ${loading ? "animate-spin" : ""}`} />
      {children}
    </button>
  );
}
