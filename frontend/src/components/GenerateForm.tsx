"use client";

import { useState, useRef, useEffect } from "react";
import type { GenerateMode } from "@/types";
import { MODELS } from "@/types";

interface GenerateFormProps {
  mode: GenerateMode;
  onSubmit: (prompt: string, model: string, imageFile?: File) => void;
  isLoading: boolean;
}

export function GenerateForm({ mode, onSubmit, isLoading }: GenerateFormProps) {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(MODELS[mode][0].value);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setModel(MODELS[mode][0].value);
    setImageFile(null);
    setImagePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [mode]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImageFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    if (mode === "image-to-video" && !imageFile) return;
    onSubmit(prompt, model, imageFile || undefined);
  };

  const models = MODELS[mode];

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label htmlFor="prompt" className="font-semibold text-gray-700">
          Prompt
        </label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe what you want to generate..."
          rows={4}
          disabled={isLoading}
          className="p-3 border border-gray-300 rounded-lg text-base resize-y min-h-[100px]
            focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
            disabled:bg-gray-100 disabled:cursor-not-allowed"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="model" className="font-semibold text-gray-700">
          Model
        </label>
        <select
          id="model"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          disabled={isLoading}
          className="p-3 border border-gray-300 rounded-lg text-base
            focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
            disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          {models.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {mode === "image-to-video" && (
        <div className="flex flex-col gap-2">
          <label className="font-semibold text-gray-700">Source Image</label>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleImageChange}
            disabled={isLoading}
            className="p-2 disabled:cursor-not-allowed"
          />
          {imagePreview && (
            <div className="mt-2 max-w-[200px]">
              <img
                src={imagePreview}
                alt="Preview"
                className="w-full rounded-lg border border-gray-300"
              />
            </div>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading || !prompt.trim() || (mode === "image-to-video" && !imageFile)}
        className="py-3 px-6 bg-blue-600 text-white rounded-lg text-base font-semibold
          hover:bg-blue-700 transition-colors
          disabled:bg-gray-400 disabled:cursor-not-allowed"
      >
        {isLoading ? "Generating..." : "Generate"}
      </button>
    </form>
  );
}
