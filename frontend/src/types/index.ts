// ===== 사용자 인증 =====

export interface User {
  id: number;
  email: string;
  username: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ===== 생성 모드 =====

export type GenerateMode = "text-to-image" | "text-to-video" | "image-to-video";

export interface JobStatus {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  asset_id?: number;
  result_url?: string;
  error_message?: string;
}

export interface GenerateResponse {
  job_id: string;
  status: string;
  created_at: string;
}

export interface ModelOption {
  value: string;
  label: string;
}

export const MODELS: Record<GenerateMode, ModelOption[]> = {
  "text-to-image": [
    { value: "imagen-3.0-fast-generate-001", label: "Imagen 3.0 Fast" }
  ],
  "text-to-video": [
    { value: "veo-3.0-fast-generate-001", label: "Veo 3.0 Fast" }
  ],
  "image-to-video": [
    { value: "veo-3.0-fast-generate-001", label: "Veo 3.0 Fast" }
  ]
};

// ===== Vertex AI 고급 옵션 (Docs 기반) =====

/** Imagen 3.0 Text-to-Image 옵션 (Python SDK inspect.signature 검증 완료) */
export interface ImageGenerationOptions {
  aspect_ratio?: string;
  negative_prompt?: string;
  seed?: number;
  guidance_scale?: number;
  safety_filter_level?: string;

  add_watermark?: boolean;
  language?: string;
}

/** Veo 3.0 Text-to-Video 옵션 */
export interface VideoGenerationOptions {
  aspect_ratio?: string;
  duration_seconds?: number;
  negative_prompt?: string;
  seed?: number;

  generate_audio?: boolean;
  resolution?: string;
}

/** Veo 3.0 Image-to-Video 옵션 */
export interface ImageToVideoOptions {
  duration_seconds?: number;
  seed?: number;

  resolution?: string;
  resize_mode?: string;
}

/** 모든 모드의 옵션 통합 타입 */
export type GenerationOptions = ImageGenerationOptions | VideoGenerationOptions | ImageToVideoOptions;

// ===== 옵션 선택지 상수 (Vertex AI Docs 기반) =====

export const IMAGE_ASPECT_RATIOS = [
  { value: "", label: "기본값 (1:1)" },
  { value: "1:1", label: "1:1 (정사각형)" },
  { value: "3:4", label: "3:4 (세로)" },
  { value: "4:3", label: "4:3 (가로)" },
  { value: "16:9", label: "16:9 (와이드)" },
  { value: "9:16", label: "9:16 (세로 와이드)" },
];

export const VIDEO_ASPECT_RATIOS = [
  { value: "", label: "기본값 (16:9)" },
  { value: "16:9", label: "16:9 (가로)" },
  { value: "9:16", label: "9:16 (세로)" },
];

export const VIDEO_DURATIONS = [
  { value: "", label: "기본값 (8초)" },
  { value: "4", label: "4초" },
  { value: "6", label: "6초" },
  { value: "8", label: "8초" },
];

export const VIDEO_RESOLUTIONS = [
  { value: "", label: "기본값 (720p)" },
  { value: "720p", label: "720p (HD)" },
  { value: "1080p", label: "1080p (Full HD)" },
];

export const SAFETY_LEVELS = [
  { value: "", label: "기본값 (중간)" },
  { value: "block_low_and_above", label: "엄격 (대부분 차단)" },
  { value: "block_medium_and_above", label: "중간 (균형)" },
  { value: "block_only_high", label: "완화 (최소 차단)" },
];

export const LANGUAGES = [
  { value: "", label: "자동 감지" },
  { value: "en", label: "English" },
  { value: "ko", label: "한국어" },
  { value: "ja", label: "日本語" },
  { value: "zh", label: "中文" },
  { value: "zh-TW", label: "中文 (繁體)" },
  { value: "hi", label: "हिन्दी" },
  { value: "pt", label: "Português" },
  { value: "es", label: "Español" },
];

export const RESIZE_MODES = [
  { value: "", label: "기본값 (패딩)" },
  { value: "pad", label: "패딩 (비율 유지, 여백 추가)" },
  { value: "crop", label: "크롭 (비율 맞춤, 일부 잘림)" },
];
