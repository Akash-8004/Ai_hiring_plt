import React from "react";
import { MarketingNav } from "./MarketingNav";
import { MarketingFooter } from "./MarketingFooter";
import "./marketing.css";

export function MarketingLayout({ children }) {
  return (
    <div className="mkt-page">
      <MarketingNav />
      {children}
      <MarketingFooter />
    </div>
  );
}
