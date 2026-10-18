import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./styles/tokens.css";

// 默认不因为窗口聚焦就重取（数据是按上游频率轮询的，聚焦重取只会制造噪声）；
// 失败只重试一次 —— risk 单次要 18 秒，多次重试会让用户等更久。
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, staleTime: 30_000, retry: 1 },
  },
});

// 生产部署在 /pumpfun/ 下，basename 必须跟 vite 的 base 一致，
// 否则 BrowserRouter 会把前缀当成路由的一部分。
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
