import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Asset Generator",
  description: "Generate game assets using Vertex AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
