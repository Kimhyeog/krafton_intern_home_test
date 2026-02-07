"use client";

import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";

export function Navbar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold text-gray-900">
          AI Asset Generator
        </Link>

        <div className="flex items-center gap-4">
          {user ? (
            <>
              <Link
                href="/"
                className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                생성
              </Link>
              <Link
                href="/my-assets"
                className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                내 에셋
              </Link>
              <span className="text-sm text-gray-400">{user.username}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-red-500 hover:text-red-700 transition-colors"
              >
                로그아웃
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                로그인
              </Link>
              <Link
                href="/signup"
                className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                회원가입
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
