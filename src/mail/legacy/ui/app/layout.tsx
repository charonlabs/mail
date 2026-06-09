import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MAIL Swarm Viewer",
  description: "Real-time visualization dashboard for MAIL multi-agent swarms",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased overflow-hidden">
        {children}
      </body>
    </html>
  );
}
