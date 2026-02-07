"use client";

import { useState, useRef, useEffect } from "react";
import type { GenerateMode, GenerationOptions } from "@/types";
import {
  MODELS,
  IMAGE_ASPECT_RATIOS,
  VIDEO_ASPECT_RATIOS,
  VIDEO_DURATIONS,
  VIDEO_RESOLUTIONS,
  SAFETY_LEVELS,

  LANGUAGES,
  RESIZE_MODES,
} from "@/types";

interface GenerateFormProps {
  mode: GenerateMode;
  onSubmit: (prompt: string, model: string, imageFile?: File, options?: GenerationOptions) => void;
  isLoading: boolean;
}

/** 드롭다운 셀렉트 컴포넌트 */
function SelectField({
  id,
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-gray-600">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="p-2 border border-gray-300 rounded-lg text-sm
          focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
          disabled:bg-gray-100 disabled:cursor-not-allowed"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function GenerateForm({ mode, onSubmit, isLoading }: GenerateFormProps) {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(MODELS[mode][0].value);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // === Imagen 3.0 옵션 (Python SDK 지원 파라미터) ===
  const [aspectRatio, setAspectRatio] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [seed, setSeed] = useState("");
  const [guidanceScale, setGuidanceScale] = useState("");
  const [safetyLevel, setSafetyLevel] = useState("");
  const [addWatermark, setAddWatermark] = useState(true);
  const [language, setLanguage] = useState("");

  // === Veo 3.0 옵션 ===
  const [duration, setDuration] = useState("");
  const [resolution, setResolution] = useState("");
  const [generateAudio, setGenerateAudio] = useState(false);
  const [resizeMode, setResizeMode] = useState("");

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

  /** 현재 모드와 설정값에서 옵션 객체 구성 */
  const buildOptions = (): GenerationOptions | undefined => {
    const opts: Record<string, unknown> = {};

    if (mode === "text-to-image") {
      if (aspectRatio) opts.aspect_ratio = aspectRatio;
      if (negativePrompt.trim()) opts.negative_prompt = negativePrompt.trim();
      if (seed) opts.seed = parseInt(seed, 10);
      if (guidanceScale) opts.guidance_scale = parseInt(guidanceScale, 10);
      if (safetyLevel) opts.safety_filter_level = safetyLevel;

      if (!addWatermark) opts.add_watermark = false;
      if (language) opts.language = language;
    }

    if (mode === "text-to-video") {
      if (aspectRatio) opts.aspect_ratio = aspectRatio;
      if (duration) opts.duration_seconds = parseInt(duration, 10);
      if (negativePrompt.trim()) opts.negative_prompt = negativePrompt.trim();
      if (seed) opts.seed = parseInt(seed, 10);

      if (generateAudio) opts.generate_audio = true;
      if (resolution) opts.resolution = resolution;
    }

    if (mode === "image-to-video") {
      if (duration) opts.duration_seconds = parseInt(duration, 10);
      if (seed) opts.seed = parseInt(seed, 10);

      if (resolution) opts.resolution = resolution;
      if (resizeMode) opts.resize_mode = resizeMode;
    }

    return Object.keys(opts).length > 0 ? (opts as GenerationOptions) : undefined;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    if (mode === "image-to-video" && !imageFile) return;
    onSubmit(prompt, model, imageFile || undefined, buildOptions());
  };

  const models = MODELS[mode];
  const isImage = mode === "text-to-image";
  const isTextToVideo = mode === "text-to-video";
  const isImageToVideo = mode === "image-to-video";

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* 프롬프트 */}
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

      {/* 모델 선택 */}
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

      {/* 이미지 업로드 (Image-to-Video) */}
      {isImageToVideo && (
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

      {/* ===== 고급 옵션 (Vertex AI Docs 기반) ===== */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full px-4 py-3 text-left text-sm font-semibold text-gray-600
            bg-gray-50 hover:bg-gray-100 transition-colors flex items-center gap-2"
        >
          <span className="text-xs">{showAdvanced ? "\u25BE" : "\u25B8"}</span>
          Advanced Options
          <span className="text-xs text-gray-400 ml-auto">Vertex AI Docs</span>
        </button>

        {showAdvanced && (
          <div className="p-4 bg-white border-t border-gray-200">
            <div className="grid grid-cols-2 gap-4">

              {/* ---- Text-to-Image 전용 옵션 ---- */}
              {isImage && (
                <>
                  <SelectField
                    id="aspectRatio"
                    label="Aspect Ratio (종횡비)"
                    value={aspectRatio}
                    onChange={setAspectRatio}
                    options={IMAGE_ASPECT_RATIOS}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="language"
                    label="Language (프롬프트 언어)"
                    value={language}
                    onChange={setLanguage}
                    options={LANGUAGES}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="safetyLevel"
                    label="Safety Filter (안전 필터)"
                    value={safetyLevel}
                    onChange={setSafetyLevel}
                    options={SAFETY_LEVELS}
                    disabled={isLoading}
                  />
                  {/* Guidance Scale (프롬프트 충실도) */}
                  <div className="flex flex-col gap-1">
                    <label htmlFor="guidanceScale" className="text-sm font-medium text-gray-600">
                      Guidance Scale ({guidanceScale || "기본값"})
                    </label>
                    <input
                      id="guidanceScale"
                      type="range"
                      min="0"
                      max="100"
                      value={guidanceScale || "50"}
                      onChange={(e) => setGuidanceScale(e.target.value)}
                      disabled={isLoading}
                      className="w-full accent-blue-600"
                    />
                    <span className="text-xs text-gray-400">낮을수록 창의적, 높을수록 프롬프트 충실</span>
                  </div>

                  {/* 시드 (결정론적 생성) */}
                  <div className="flex flex-col gap-1">
                    <label htmlFor="seed" className="text-sm font-medium text-gray-600">
                      Seed (결정론적 생성)
                    </label>
                    <input
                      id="seed"
                      type="number"
                      min="1"
                      max="2147483647"
                      value={seed}
                      onChange={(e) => {
                        setSeed(e.target.value);
                        if (e.target.value) setAddWatermark(false);
                      }}
                      placeholder="비워두면 랜덤"
                      disabled={isLoading}
                      className="p-2 border border-gray-300 rounded-lg text-sm
                        focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
                        disabled:bg-gray-100 disabled:cursor-not-allowed"
                    />
                  </div>

                  {/* 네거티브 프롬프트 */}
                  <div className="col-span-2 flex flex-col gap-1">
                    <label htmlFor="negativePrompt" className="text-sm font-medium text-gray-600">
                      Negative Prompt (제외할 요소)
                    </label>
                    <textarea
                      id="negativePrompt"
                      value={negativePrompt}
                      onChange={(e) => setNegativePrompt(e.target.value)}
                      placeholder="생성에서 제외하고 싶은 요소를 입력하세요..."
                      rows={2}
                      disabled={isLoading}
                      className="p-2 border border-gray-300 rounded-lg text-sm resize-y
                        focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
                        disabled:bg-gray-100 disabled:cursor-not-allowed"
                    />
                  </div>

                  {/* SynthID 워터마크 토글 */}
                  <div className="col-span-2">
                    <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={addWatermark}
                        onChange={(e) => setAddWatermark(e.target.checked)}
                        disabled={isLoading || !!seed}
                        className="accent-blue-600 w-4 h-4"
                      />
                      SynthID Watermark (디지털 워터마크)
                      {seed && <span className="text-xs text-amber-600">(Seed 사용 시 비활성)</span>}
                    </label>
                  </div>
                </>
              )}

              {/* ---- Text-to-Video 전용 옵션 ---- */}
              {isTextToVideo && (
                <>
                  <SelectField
                    id="aspectRatio"
                    label="Aspect Ratio (종횡비)"
                    value={aspectRatio}
                    onChange={setAspectRatio}
                    options={VIDEO_ASPECT_RATIOS}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="duration"
                    label="Duration (영상 길이)"
                    value={duration}
                    onChange={setDuration}
                    options={VIDEO_DURATIONS}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="resolution"
                    label="Resolution (해상도)"
                    value={resolution}
                    onChange={setResolution}
                    options={VIDEO_RESOLUTIONS}
                    disabled={isLoading}
                  />
                  {/* 시드 */}
                  <div className="flex flex-col gap-1">
                    <label htmlFor="seed" className="text-sm font-medium text-gray-600">
                      Seed (결정론적 생성)
                    </label>
                    <input
                      id="seed"
                      type="number"
                      min="0"
                      max="4294967295"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value)}
                      placeholder="비워두면 랜덤"
                      disabled={isLoading}
                      className="p-2 border border-gray-300 rounded-lg text-sm
                        focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
                        disabled:bg-gray-100 disabled:cursor-not-allowed"
                    />
                  </div>

                  {/* 네거티브 프롬프트 */}
                  <div className="col-span-2 flex flex-col gap-1">
                    <label htmlFor="negativePrompt" className="text-sm font-medium text-gray-600">
                      Negative Prompt (제외할 요소)
                    </label>
                    <textarea
                      id="negativePrompt"
                      value={negativePrompt}
                      onChange={(e) => setNegativePrompt(e.target.value)}
                      placeholder="생성에서 제외하고 싶은 요소를 입력하세요..."
                      rows={2}
                      disabled={isLoading}
                      className="p-2 border border-gray-300 rounded-lg text-sm resize-y
                        focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
                        disabled:bg-gray-100 disabled:cursor-not-allowed"
                    />
                  </div>

                  {/* 오디오 생성 토글 */}
                  <div className="col-span-2">
                    <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={generateAudio}
                        onChange={(e) => setGenerateAudio(e.target.checked)}
                        disabled={isLoading}
                        className="accent-blue-600 w-4 h-4"
                      />
                      Generate Audio (Veo 3.0 오디오 동시 생성)
                    </label>
                  </div>
                </>
              )}

              {/* ---- Image-to-Video 전용 옵션 ---- */}
              {isImageToVideo && (
                <>
                  <SelectField
                    id="duration"
                    label="Duration (영상 길이)"
                    value={duration}
                    onChange={setDuration}
                    options={VIDEO_DURATIONS}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="resolution"
                    label="Resolution (해상도)"
                    value={resolution}
                    onChange={setResolution}
                    options={VIDEO_RESOLUTIONS}
                    disabled={isLoading}
                  />
                  <SelectField
                    id="resizeMode"
                    label="Resize Mode (비율 조정)"
                    value={resizeMode}
                    onChange={setResizeMode}
                    options={RESIZE_MODES}
                    disabled={isLoading}
                  />

                  {/* 시드 */}
                  <div className="flex flex-col gap-1">
                    <label htmlFor="seed" className="text-sm font-medium text-gray-600">
                      Seed (결정론적 생성)
                    </label>
                    <input
                      id="seed"
                      type="number"
                      min="0"
                      max="4294967295"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value)}
                      placeholder="비워두면 랜덤"
                      disabled={isLoading}
                      className="p-2 border border-gray-300 rounded-lg text-sm
                        focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-100
                        disabled:bg-gray-100 disabled:cursor-not-allowed"
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 생성 버튼 */}
      <button
        type="submit"
        disabled={isLoading || !prompt.trim() || (isImageToVideo && !imageFile)}
        className="py-3 px-6 bg-blue-600 text-white rounded-lg text-base font-semibold
          hover:bg-blue-700 transition-colors
          disabled:bg-gray-400 disabled:cursor-not-allowed"
      >
        {isLoading ? "Generating..." : "Generate"}
      </button>
    </form>
  );
}
