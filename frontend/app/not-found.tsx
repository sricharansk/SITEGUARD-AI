import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-lg px-4 py-16">
      <h1 className="text-xl font-bold">Page not found</h1>
      <p className="mt-2 text-slate-700">The page does not exist or you do not have access to it.</p>
      <Link href="/dashboard" className="btn-primary mt-4">
        Go to the dashboard
      </Link>
    </main>
  );
}
