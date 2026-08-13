import React from "react";
import { Loader2 } from "lucide-react";

export function LoadingScreen() {
  return (
    <div className="loading-screen">
      <Loader2 className="spin" size={28} />
      <strong>Loading workspace</strong>
    </div>
  );
}
