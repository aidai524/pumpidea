import { Link, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Analysis } from "./routes/Analysis";
import { Audit } from "./routes/Audit";
import { Overview } from "./routes/Overview";
import { Pulse } from "./routes/Pulse";
import { Risk } from "./routes/Risk";

function NotFound() {
  return (
    <div className="py-16 text-center">
      <div className="text-13 text-sub">这个地址没有内容</div>
      <Link to="/" className="mt-3 inline-block text-12 text-accent">
        回到总览 →
      </Link>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="analysis" element={<Analysis />} />
        <Route path="audit" element={<Audit />} />
        <Route path="pulse" element={<Pulse />} />
        <Route path="risk" element={<Risk />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
