import "./globals.css";

export const metadata = {
  title: "Lauds",
  description: "Sample-data preview of Lauds, hosted on Vercel",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
