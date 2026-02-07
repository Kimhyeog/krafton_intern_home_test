"use client";

import type { JobStatus, GenerateMode } from "@/types";
import { getAssetUrl } from "@/lib/api";

interface ResultDisplayProps {
  jobStatus: JobStatus | null;
  mode: GenerateMode;
  error: string | null;
}

export function ResultDisplay({ jobStatus, mode, error }: ResultDisplayProps) {
  if (error) {
    return (
      <div className="mt-8 min-h-[300px]">
        <div className="flex flex-col items-center justify-center h-[300px] bg-red-50 border border-red-200 rounded-xl gap-2">
          <span className="flex items-center justify-center w-12 h-12 bg-red-600 text-white rounded-full text-2xl font-bold">
            !
          </span>
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!jobStatus) {
    return (
      <div className="mt-8 min-h-[300px]">
        <div className="flex items-center justify-center h-[300px] bg-gray-50 border-2 border-dashed border-gray-200 rounded-xl text-gray-400">
          <p>Generated content will appear here</p>
        </div>
      </div>
    );
  }

  if (jobStatus.status === "pending" || jobStatus.status === "processing") {
    return (
      <div className="mt-8 min-h-[300px]">
        <div className="flex flex-col items-center justify-center h-[300px] bg-gray-50 rounded-xl gap-4">
          <div className="w-12 h-12 border-4 border-gray-200 border-t-blue-600 rounded-full animate-spin" />
          <p className="text-gray-700">
            {jobStatus.status === "pending" ? "Pending..." : "Processing..."}
          </p>
          <p className="text-gray-400 text-sm">
            {mode === "text-to-image"
              ? "Image generation takes 5-10 seconds"
              : "Video generation takes 1-3 minutes"}
          </p>
        </div>
      </div>
    );
  }

  if (jobStatus.status === "completed" && jobStatus.result_url) {
    const assetUrl = getAssetUrl(jobStatus.result_url);
    const isVideo = mode === "text-to-video" || mode === "image-to-video";

    return (
      <div className="mt-8 min-h-[300px]">
        <div className="flex justify-center">
          {isVideo ? (
            <video
              src={assetUrl}
              controls
              autoPlay
              loop
              className="max-w-full max-h-[600px] rounded-xl shadow-lg"
            />
          ) : (
            <img
              src={assetUrl}
              alt="Generated content"
              className="max-w-full max-h-[600px] rounded-xl shadow-lg"
            />
          )}
        </div>
      </div>
    );
  }

  if (jobStatus.status === "failed") {
    return (
      <div className="mt-8 min-h-[300px]">
        <div className="flex flex-col items-center justify-center h-[300px] bg-red-50 border border-red-200 rounded-xl gap-2">
          <span className="flex items-center justify-center w-12 h-12 bg-red-600 text-white rounded-full text-2xl font-bold">
            !
          </span>
          <p className="text-red-600 font-semibold">생성 실패</p>
          {jobStatus.error_message && (
            <p className="text-red-800 text-sm max-w-[480px] text-center leading-relaxed">
              {jobStatus.error_message}
            </p>
          )}
        </div>
      </div>
    );
  }

  return null;
}
