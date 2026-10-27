import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { createQueryClient } from "@/api/queryClient";
import { App } from "./App";
import { AppProviders } from "./AppProviders";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <AppProviders client={createQueryClient()}>
        <App />
      </AppProviders>
    </BrowserRouter>
  </StrictMode>,
);
