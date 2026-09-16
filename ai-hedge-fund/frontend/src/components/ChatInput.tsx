import { useState, type FormEvent } from "react";

interface Props {
  onSubmit: (query: string) => void;
  placeholder?: string;
}

export function ChatInput({
  onSubmit,
  placeholder = "Check AAPL, Scan value stocks...",
}: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value.trim());
      setValue("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="relative">
      <div className="flex items-center gap-3 bg-surface-card border border-border rounded-xl px-4 py-3 focus-within:border-accent-blue transition-colors">
        <svg
          className="w-5 h-5 text-accent-blue shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
          />
        </svg>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="grow bg-transparent text-white placeholder-gray-500 outline-none text-sm"
        />
        <kbd className="text-xs text-gray-600 bg-surface-elevated px-1.5 py-0.5 rounded font-mono">
          Enter
        </kbd>
      </div>
    </form>
  );
}
