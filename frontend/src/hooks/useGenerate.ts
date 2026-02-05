"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { generate as apiGenerate, getJobStatus } from "@/lib/api";
import type { GenerateMode, JobStatus } from "@/types";

const POLLING_INTERVAL = 2000;

export function useGenerate() {
  const [isLoading, setIsLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const generate = useCallback(
    async (mode: GenerateMode, prompt: string, model: string, imageFile?: File) => {
      stopPolling();
      setError(null);
      setIsLoading(true);
      setJobStatus(null);

      try {
        const res = await apiGenerate(mode, prompt, model, imageFile);
        setJobStatus({ job_id: res.job_id, status: "pending" });

        pollingRef.current = setInterval(async () => {
          try {
            const status = await getJobStatus(res.job_id);
            setJobStatus(status);

            if (status.status === "completed" || status.status === "failed") {
              stopPolling();
              setIsLoading(false);

              if (status.status === "failed") {
                setError(status.error_message || "Generation failed");
              }
            }
          } catch (err) {
            console.error("Polling error:", err);
          }
        }, POLLING_INTERVAL);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        setIsLoading(false);
      }
    },
    [stopPolling]
  );

  const reset = useCallback(() => {
    stopPolling();
    setIsLoading(false);
    setJobStatus(null);
    setError(null);
  }, [stopPolling]);

  return { generate, isLoading, jobStatus, error, reset };
}
