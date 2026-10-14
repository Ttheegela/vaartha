import { ImageResponse } from "next/og"

const BG = "#0a0a0a"
const FG = "#f5f5f5"
const MARK_RATIO = 0.53 // font size relative to icon edge (17/32 in icon.svg)

/** The Vārtā "Vā" mark as a square PNG of `size` px; `radius` rounds the corners (0 for full-bleed). */
export function markImage(size: number, radius = 0): ImageResponse {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: BG, borderRadius: radius, color: FG, fontFamily: "Georgia, 'Times New Roman', serif", fontSize: size * MARK_RATIO, letterSpacing: -size * 0.012 }}>
        V<span style={{ fontStyle: "italic" }}>ā</span>
      </div>
    ),
    { width: size, height: size },
  )
}
