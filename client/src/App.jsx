import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigationType } from "react-router-dom";
import HomePage from "@/pages/HomePage.jsx";
import LogsPage from "@/pages/LogsPage.jsx";
import { logAudit } from "@/lib/siteLogger";

function NavigationAudit() {
  const loc = useLocation();
  const navType = useNavigationType();
  useEffect(() => {
    logAudit("nav:route", "Application route changed", {
      pathname: loc.pathname,
      search: loc.search || "",
      hash: loc.hash || "",
      navType,
    });
  }, [loc.pathname, loc.search, loc.hash, navType]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <NavigationAudit />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
