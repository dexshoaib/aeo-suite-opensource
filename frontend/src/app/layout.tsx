import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AEO Suite",
  description: "AI answer engine optimization: audit, measure, fix, publish.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
