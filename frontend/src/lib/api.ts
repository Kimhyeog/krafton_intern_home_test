import type { GenerateMode, GenerateResponse, JobStatus, GenerationOptions, User, TokenResponse } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ===== 토큰 관리 (모듈 스코프) =====

let accessToken: string | null = null;
let onAuthError: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setOnAuthError(callback: (() => void) | null) {
  onAuthError = callback;
}

// ===== Silent Refresh + 인증 래퍼 =====

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (res.ok) {
      const data: TokenResponse = await res.json();
      accessToken = data.access_token;
      localStorage.setItem("refresh_token", data.refresh_token);
      return true;
    }
  } catch {
    // refresh 실패
  }

  // refresh 실패 → 로그아웃
  accessToken = null;
  localStorage.removeItem("refresh_token");
  if (onAuthError) onAuthError();
  return false;
}

export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401 && accessToken) {
    // Access Token 만료 → Refresh 시도
    const refreshed = await tryRefresh();
    if (refreshed) {
      const retryHeaders = new Headers(options.headers);
      retryHeaders.set("Authorization", `Bearer ${accessToken}`);
      res = await fetch(url, { ...options, headers: retryHeaders });
    }
  }

  return res;
}

// ===== 인증 API =====

export async function authSignup(email: string, username: string, password: string): Promise<User> {
  const res = await fetch(`${API_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, username, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "회원가입 실패");
  }
  return res.json();
}

export async function authLogin(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "로그인 실패");
  }
  return res.json();
}

export async function authLogout(refreshToken: string): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function authMe(): Promise<User> {
  const res = await fetchWithAuth(`${API_URL}/api/auth/me`);
  if (!res.ok) throw new Error("사용자 정보 조회 실패");
  return res.json();
}

// ===== 에셋 API (인증 필요) =====

export interface Asset {
  id: number;
  jobId: string;
  filePath: string;
  prompt: string;
  model: string;
  assetType: string;
  createdAt: string;
  fileSize: number | null;
  duration: number | null;
  userId: number | null;
}

export async function listMyAssets(skip = 0, limit = 20): Promise<Asset[]> {
  const res = await fetchWithAuth(`${API_URL}/api/assets/?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error("에셋 목록 조회 실패");
  return res.json();
}

export async function deleteAsset(assetId: number): Promise<void> {
  const res = await fetchWithAuth(`${API_URL}/api/assets/${assetId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("에셋 삭제 실패");
}

// ===== 생성 옵션 유틸 =====

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

// ===== 생성 API (인증 필요) =====

export async function generateTextToImage(
  prompt: string,
  model: string,
  options?: GenerationOptions
): Promise<GenerateResponse> {
  const body: Record<string, unknown> = { prompt, model, ...cleanOptions(options) };

  const res = await fetchWithAuth(`${API_URL}/api/generate/text-to-image`, {
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

  const res = await fetchWithAuth(`${API_URL}/api/generate/text-to-video`, {
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

  // FormData는 Content-Type 자동 설정이므로 headers에 명시하지 않음
  const headers = new Headers();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const res = await fetch(`${API_URL}/api/generate/image-to-video`, {
    method: "POST",
    headers,
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
