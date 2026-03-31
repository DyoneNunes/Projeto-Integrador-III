"use client";

import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

export default function RefreshButton() {
  const router = useRouter();

  return (
    <button
      onClick={() => router.refresh()}
      className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors"
    >
      <RefreshCw className="h-3.5 w-3.5" />
      Refresh
    </button>
  );
}