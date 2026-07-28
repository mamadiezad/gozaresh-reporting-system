import BackendRequired from "@/components/BackendRequired";

import DashboardClient from "./DashboardClient";

/**
 * The dashboard needs a live backend. The GitHub Pages build (STATIC_EXPORT)
 * has none, so it renders setup instructions instead of a login form that
 * could only ever fail with "Failed to fetch".
 *
 * The dashboard code is still bundled here (~35 kB) because the import is
 * static; that is an acceptable trade for keeping a single source of truth,
 * and the chunk is never executed on Pages.
 *
 * `docker compose up` and `npm run dev` render the real dashboard.
 */
const isStaticExport = process.env.STATIC_EXPORT === "true";

export default function AppPage() {
  return isStaticExport ? <BackendRequired /> : <DashboardClient />;
}
