"use client";

import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function SignupPage() {
  const { signup, user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // 이미 로그인 상태면 메인으로
  if (user) {
    router.replace("/");
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== passwordConfirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }

    if (password.length < 6) {
      setError("비밀번호는 6자 이상이어야 합니다.");
      return;
    }

    setIsLoading(true);

    try {
      await signup(email, username, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입 실패");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md bg-white p-8 rounded-2xl shadow-sm">
        <h1 className="text-2xl font-bold text-gray-900 text-center mb-2">
          AI Asset Generator
        </h1>
        <p className="text-gray-500 text-center mb-8">회원가입</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="email" className="text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="user@example.com"
              disabled={isLoading}
              className="p-3 border border-gray-300 rounded-lg text-base
                focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
                disabled:bg-gray-100"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="username" className="text-sm font-medium text-gray-700">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              placeholder="닉네임을 입력하세요"
              disabled={isLoading}
              className="p-3 border border-gray-300 rounded-lg text-base
                focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
                disabled:bg-gray-100"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="6자 이상"
              disabled={isLoading}
              className="p-3 border border-gray-300 rounded-lg text-base
                focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
                disabled:bg-gray-100"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="passwordConfirm" className="text-sm font-medium text-gray-700">
              Password Confirm
            </label>
            <input
              id="passwordConfirm"
              type="password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              required
              placeholder="비밀번호를 다시 입력하세요"
              disabled={isLoading}
              className="p-3 border border-gray-300 rounded-lg text-base
                focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100
                disabled:bg-gray-100"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="py-3 bg-blue-600 text-white rounded-lg font-semibold
              hover:bg-blue-700 transition-colors
              disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isLoading ? "가입 중..." : "회원가입"}
          </button>
        </form>

        <p className="text-sm text-gray-500 text-center mt-6">
          이미 계정이 있으신가요?{" "}
          <Link href="/login" className="text-blue-600 hover:underline">
            로그인
          </Link>
        </p>
      </div>
    </main>
  );
}
