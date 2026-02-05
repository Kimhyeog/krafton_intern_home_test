"use client";

import { useState } from "react";
import { TabMenu } from "@/components/TabMenu";
import { GenerateForm } from "@/components/GenerateForm";
import { ResultDisplay } from "@/components/ResultDisplay";
import { useGenerate } from "@/hooks/useGenerate";
import type { GenerateMode } from "@/types";

export default function Home() {
  const [mode, setMode] = useState<GenerateMode>("text-to-image");
  const { generate, isLoading, jobStatus, error, reset } = useGenerate();

  const handleModeChange = (newMode: GenerateMode) => {
    reset();
    setMode(newMode);
  };

  const handleSubmit = (prompt: string, model: string, imageFile?: File) => {
    generate(mode, prompt, model, imageFile);
  };

  return (
    <main className="min-h-screen p-8 bg-gray-50">
      <div className="max-w-3xl mx-auto bg-white p-8 rounded-2xl shadow-sm">
        <h1 className="text-3xl font-bold text-gray-900">AI Asset Generator</h1>
        <p className="text-gray-500 mt-2 mb-6">
          Generate game assets using Vertex AI
        </p>

        <TabMenu
          activeMode={mode}
          onModeChange={handleModeChange}
          disabled={isLoading}
        />

        <GenerateForm
          mode={mode}
          onSubmit={handleSubmit}
          isLoading={isLoading}
        />

        <ResultDisplay
          jobStatus={jobStatus}
          mode={mode}
          error={error}
        />
      </div>
    </main>
  );
}
