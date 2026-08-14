import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { RouteFallback } from "./components/states";
import { ToastProvider } from "./components/toast";
import "./index.css";

const Customers = lazy(() => import("./pages/Customers"));
const CustomerDetail = lazy(() => import("./pages/CustomerDetail"));
const ComingSoon = lazy(() => import("./pages/ComingSoon"));
const Dashboard = lazy(() => import("./pages/Dashboard"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={<RouteFallback />}>
            <Customers />
          </Suspense>
        ),
      },
      {
        path: "customers/:id",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <CustomerDetail />
          </Suspense>
        ),
      },
      {
        path: "dashboard",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <Dashboard />
          </Suspense>
        ),
      },
      {
        path: "reports",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <ComingSoon title="Reports" note="Forward-ETL controls land in T7." />
          </Suspense>
        ),
      },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
