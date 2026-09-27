import "./globals.css";

export const metadata = {
  title: "Laude",
  description: "Sample-data preview of Laude, hosted on Vercel",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
