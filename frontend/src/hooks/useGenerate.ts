"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { generate as apiGenerate, getJobStatus } from "@/lib/api";
import type { GenerateMode, JobStatus, GenerationOptions } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useGenerate() {
  const [isLoading, setIsLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  // 컴포넌트 언마운트 시 SSE 연결 정리
  useEffect(() => {
    return () => stopStreaming();
  }, [stopStreaming]);

  const generate = useCallback(
    async (mode: GenerateMode, prompt: string, model: string, imageFile?: File, options?: GenerationOptions) => {
      stopStreaming();
      setError(null);
      setIsLoading(true);
      setJobStatus(null);

      try {
        const res = await apiGenerate(mode, prompt, model, imageFile, options);

        // 캐시 히트: 서버가 즉시 completed를 반환한 경우
        if (res.status === "completed") {
          const status = await getJobStatus(res.job_id);
          setJobStatus(status);
          setIsLoading(false);
          return;
        }

        setJobStatus({ job_id: res.job_id, status: "pending" });

        // SSE 연결로 실시간 상태 수신
        const eventSource = new EventSource(
          `${API_URL}/api/generate/jobs/${res.job_id}/stream`
        );
        eventSourceRef.current = eventSource;

        eventSource.onmessage = (event) => {
          const status: JobStatus = JSON.parse(event.data);
          setJobStatus(status);

          if (status.status === "completed" || status.status === "failed") {
            eventSource.close();
            eventSourceRef.current = null;
            setIsLoading(false);

            if (status.status === "failed") {
              setError(status.error_message || "생성 실패");
            }
          }
        };

        eventSource.onerror = () => {
          eventSource.close();
          eventSourceRef.current = null;
          setError("서버 연결이 끊어졌습니다.");
          setIsLoading(false);
        };
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        setIsLoading(false);
      }
    },
    [stopStreaming]
  );

  const reset = useCallback(() => {
    stopStreaming();
    setIsLoading(false);
    setJobStatus(null);
    setError(null);
  }, [stopStreaming]);

  return { generate, isLoading, jobStatus, error, reset };
}
