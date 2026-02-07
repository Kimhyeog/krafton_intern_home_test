import type { GenerateMode, GenerateResponse, JobStatus, GenerationOptions } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** 빈 문자열 값 제거 — 백엔드에 불필요한 기본값을 전송하지 않음 */
function cleanOptions(options?: GenerationOptions): Record<string, unknown> | undefined {
  if (!options) return undefined;
  const cleaned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(options)) {
    if (value !== undefined && value !== null && value !== "") {
      cleaned[key] = value;
    }
  }
  return Object.keys(cleaned).length > 0 ? cleaned : undefined;
}

export async function generateTextToImage(
  prompt: string,
  model: string,
  options?: GenerationOptions
): Promise<GenerateResponse> {
  const body: Record<string, unknown> = { prompt, model, ...cleanOptions(options) };

  const res = await fetch(`${API_URL}/api/generate/text-to-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to generate image");
  return res.json();
}

export async function generateTextToVideo(
  prompt: string,
  model: string,
  options?: GenerationOptions
): Promise<GenerateResponse> {
  const body: Record<string, unknown> = { prompt, model, ...cleanOptions(options) };

  const res = await fetch(`${API_URL}/api/generate/text-to-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to generate video");
  return res.json();
}

export async function generateImageToVideo(
  prompt: string,
  model: string,
  imageFile: File,
  options?: GenerationOptions
): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("prompt", prompt);
  formData.append("model", model);
  formData.append("image", imageFile);

  // 옵션을 개별 Form 필드로 추가
  const cleaned = cleanOptions(options);
  if (cleaned) {
    for (const [key, value] of Object.entries(cleaned)) {
      formData.append(key, String(value));
    }
  }

  const res = await fetch(`${API_URL}/api/generate/image-to-video`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Failed to generate video from image");
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/api/generate/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to get job status");
  return res.json();
}

export function getAssetUrl(path: string): string {
  return `${API_URL}${path}`;
}

export async function generate(
  mode: GenerateMode,
  prompt: string,
  model: string,
  imageFile?: File,
  options?: GenerationOptions
): Promise<GenerateResponse> {
  switch (mode) {
    case "text-to-image":
      return generateTextToImage(prompt, model, options);
    case "text-to-video":
      return generateTextToVideo(prompt, model, options);
    case "image-to-video":
      if (!imageFile) throw new Error("Image file is required");
      return generateImageToVideo(prompt, model, imageFile, options);
  }
}
