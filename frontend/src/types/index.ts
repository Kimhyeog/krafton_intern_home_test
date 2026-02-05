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
