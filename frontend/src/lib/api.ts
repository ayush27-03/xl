import type { AnalysisResponse } from "./types";

export type ProgressPhase = "idle" | "uploading" | "processing" | "complete" | "error";

export interface CompareProgress {
  phase: ProgressPhase;
  value: number;
  label: string;
}

export interface CompareOptions {
  aiEnabled?: boolean;
  aiModel?: string;
  anchor?: string;
}

export function compareWorkbooks(
  left: File,
  right: File,
  options: CompareOptions,
  onProgress: (progress: CompareProgress) => void
): Promise<AnalysisResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("left_file", left);
    form.append("right_file", right);

    const params = new URLSearchParams();
    if (options.aiEnabled) {
      params.set("ai", "true");
      params.set("ai_model", options.aiModel ?? "llama3.2");
    }
    if (options.anchor) params.set("anchor", options.anchor);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/compare${params.size ? `?${params.toString()}` : ""}`);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress({
          phase: "uploading",
          value: Math.min(70, Math.round((event.loaded / event.total) * 70)),
          label: "Uploading workbooks"
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress({ phase: "complete", value: 100, label: "Analysis complete" });
        resolve(xhr.response as AnalysisResponse);
        return;
      }
      onProgress({ phase: "error", value: 100, label: "Analysis failed" });
      const detail = xhr.response?.detail ?? xhr.statusText;
      reject(new Error(typeof detail === "string" ? detail : "Unable to compare workbooks"));
    };

    xhr.onerror = () => {
      onProgress({ phase: "error", value: 100, label: "Network error" });
      reject(new Error("Could not reach the analysis API"));
    };

    xhr.onloadstart = () => onProgress({ phase: "uploading", value: 8, label: "Preparing upload" });
    xhr.onreadystatechange = () => {
      if (xhr.readyState === XMLHttpRequest.HEADERS_RECEIVED) {
        onProgress({ phase: "processing", value: 82, label: "Engine is comparing workbooks" });
      }
    };

    xhr.send(form);
  });
}
