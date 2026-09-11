import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { MarketingNav } from "./MarketingNav";
import { MarketingFooter } from "./MarketingFooter";
import "./marketing.css";

export function MarketingLayout({ children }) {
  const { hash } = useLocation();

  useEffect(() => {
    if (hash) {
      const id = hash.replace("#", "");
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      }
    } else {
      window.scrollTo(0, 0);
    }
  }, [hash]);

  return (
    <div className="mkt-page">
      <MarketingNav />
      {children}
      <MarketingFooter />
    </div>
  );
}