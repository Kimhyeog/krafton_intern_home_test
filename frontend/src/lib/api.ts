import type { GenerateMode, GenerateResponse, JobStatus } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function generateTextToImage(prompt: string, model: string): Promise<GenerateResponse> {
  const res = await fetch(`${API_URL}/api/generate/text-to-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, model }),
  });
  if (!res.ok) throw new Error("Failed to generate image");
  return res.json();
}

export async function generateTextToVideo(prompt: string, model: string): Promise<GenerateResponse> {
  const res = await fetch(`${API_URL}/api/generate/text-to-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, model }),
  });
  if (!res.ok) throw new Error("Failed to generate video");
  return res.json();
}

export async function generateImageToVideo(
  prompt: string,
  model: string,
  imageFile: File
): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("prompt", prompt);
  formData.append("model", model);
  formData.append("image", imageFile);

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
  imageFile?: File
): Promise<GenerateResponse> {
  switch (mode) {
    case "text-to-image":
      return generateTextToImage(prompt, model);
    case "text-to-video":
      return generateTextToVideo(prompt, model);
    case "image-to-video":
      if (!imageFile) throw new Error("Image file is required");
      return generateImageToVideo(prompt, model, imageFile);
  }
}
