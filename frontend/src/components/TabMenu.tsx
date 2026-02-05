"use client";

import type { GenerateMode } from "@/types";

interface TabMenuProps {
  activeMode: GenerateMode;
  onModeChange: (mode: GenerateMode) => void;
  disabled?: boolean;
}

const TABS: { mode: GenerateMode; label: string }[] = [
  { mode: "text-to-image", label: "Text to Image" },
  { mode: "text-to-video", label: "Text to Video" },
  { mode: "image-to-video", label: "Image to Video" },
];

export function TabMenu({ activeMode, onModeChange, disabled }: TabMenuProps) {
  return (
    <div className="flex border-b-2 border-gray-200 mb-6">
      {TABS.map(({ mode, label }) => (
        <button
          key={mode}
          className={`px-6 py-3 text-base border-b-2 -mb-[2px] transition-all
            ${activeMode === mode
              ? "text-blue-600 border-blue-600 font-semibold"
              : "text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50"
            }
            ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          `}
          onClick={() => onModeChange(mode)}
          disabled={disabled}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
