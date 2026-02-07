"use client";

import { useState, useEffect, useCallback } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { listMyAssets, deleteAsset, getAssetUrl, type Asset } from "@/lib/api";

// ===== 라이트박스 모달 =====

function AssetModal({
  asset,
  onClose,
  onDelete,
  isDeleting,
}: {
  asset: Asset;
  onClose: () => void;
  onDelete: (id: number) => void;
  isDeleting: boolean;
}) {
  // ESC 키로 닫기
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    // 스크롤 방지
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const url = getAssetUrl(asset.filePath);
  const isVideo = asset.assetType === "video";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 닫기 버튼 */}
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white/80 hover:text-white text-2xl
            w-8 h-8 flex items-center justify-center transition-colors"
        >
          X
        </button>

        {/* 원본 미디어 */}
        {isVideo ? (
          <video
            src={url}
            controls
            autoPlay
            className="max-w-[90vw] max-h-[70vh] rounded-xl"
          />
        ) : (
          <img
            src={url}
            alt={asset.prompt}
            className="max-w-[90vw] max-h-[70vh] rounded-xl object-contain"
          />
        )}

        {/* 상세 정보 */}
        <div className="mt-4 w-full max-w-xl text-center">
          <p className="text-white text-sm leading-relaxed mb-2">
            {asset.prompt}
          </p>
          <div className="flex items-center justify-center gap-3 text-white/60 text-xs">
            <span>{asset.model}</span>
            <span>-</span>
            <span className={isVideo ? "text-purple-300" : "text-blue-300"}>
              {asset.assetType}
            </span>
            <span>-</span>
            <span>{new Date(asset.createdAt).toLocaleDateString("ko-KR")}</span>
          </div>
          <button
            onClick={() => onDelete(asset.id)}
            disabled={isDeleting}
            className="mt-3 text-xs text-red-400 hover:text-red-300 transition-colors
              disabled:text-gray-500 disabled:cursor-not-allowed"
          >
            {isDeleting ? "삭제 중..." : "삭제"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ===== 내 에셋 페이지 =====

function MyAssetsContent() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  const PAGE_SIZE = 12;

  const loadAssets = useCallback(async (reset = false) => {
    try {
      setIsLoading(true);
      const skip = reset ? 0 : assets.length;
      const data = await listMyAssets(skip, PAGE_SIZE);
      if (reset) {
        setAssets(data);
      } else {
        setAssets((prev) => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE_SIZE);
    } catch {
      setError("에셋 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [assets.length]);

  useEffect(() => {
    loadAssets(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (assetId: number) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;

    setDeletingId(assetId);
    try {
      await deleteAsset(assetId);
      setAssets((prev) => prev.filter((a) => a.id !== assetId));
      // 모달에서 삭제한 경우 모달 닫기
      if (selectedAsset?.id === assetId) {
        setSelectedAsset(null);
      }
    } catch {
      setError("삭제에 실패했습니다.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          내 에셋 ({assets.length}개)
        </h1>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg mb-4">{error}</p>
      )}

      {assets.length === 0 && !isLoading ? (
        <div className="flex items-center justify-center h-[300px] bg-gray-50 border-2 border-dashed border-gray-200 rounded-xl text-gray-400">
          <p>아직 생성한 에셋이 없습니다.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {assets.map((asset) => (
              <div
                key={asset.id}
                className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm
                  cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => setSelectedAsset(asset)}
              >
                {/* 미리보기 */}
                <div className="h-48 bg-gray-100 flex items-center justify-center overflow-hidden">
                  {asset.assetType === "image" ? (
                    <img
                      src={getAssetUrl(asset.filePath)}
                      alt={asset.prompt}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <video
                      src={getAssetUrl(asset.filePath)}
                      className="w-full h-full object-cover"
                      muted
                      loop
                      onMouseEnter={(e) => (e.target as HTMLVideoElement).play()}
                      onMouseLeave={(e) => {
                        const v = e.target as HTMLVideoElement;
                        v.pause();
                        v.currentTime = 0;
                      }}
                    />
                  )}
                </div>

                {/* 정보 */}
                <div className="p-3">
                  <p className="text-sm text-gray-800 line-clamp-2 mb-1">
                    {asset.prompt}
                  </p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        asset.assetType === "image"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-purple-100 text-purple-700"
                      }`}>
                        {asset.assetType}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(asset.createdAt).toLocaleDateString("ko-KR")}
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(asset.id);
                      }}
                      disabled={deletingId === asset.id}
                      className="text-xs text-red-500 hover:text-red-700 transition-colors
                        disabled:text-gray-400 disabled:cursor-not-allowed"
                    >
                      {deletingId === asset.id ? "삭제 중..." : "삭제"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* 더 보기 */}
          {hasMore && (
            <div className="flex justify-center mt-6">
              <button
                onClick={() => loadAssets(false)}
                disabled={isLoading}
                className="px-6 py-2 border border-gray-300 rounded-lg text-sm text-gray-600
                  hover:bg-gray-50 transition-colors
                  disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                {isLoading ? "불러오는 중..." : "더 보기"}
              </button>
            </div>
          )}
        </>
      )}

      {/* 라이트박스 모달 */}
      {selectedAsset && (
        <AssetModal
          asset={selectedAsset}
          onClose={() => setSelectedAsset(null)}
          onDelete={handleDelete}
          isDeleting={deletingId === selectedAsset.id}
        />
      )}
    </div>
  );
}

export default function MyAssetsPage() {
  return (
    <AuthGuard>
      <MyAssetsContent />
    </AuthGuard>
  );
}
