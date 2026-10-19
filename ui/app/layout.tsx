import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MAST-Scope — flight recorder",
  description: "Replay a multi-agent failure, see the first fault, and the repair of that sub-task.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
