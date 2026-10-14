import type { MetadataRoute } from "next"

const THEME = "#0a0a0a"

/** Web app manifest so the owner instance installs as a Dock / home-screen app. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vārtā",
    short_name: "Vārtā",
    start_url: "/",
    display: "standalone",
    background_color: THEME,
    theme_color: THEME,
    icons: [
      { src: "/icon/192", sizes: "192x192", type: "image/png" },
      { src: "/icon/512", sizes: "512x512", type: "image/png" },
    ],
  }
}
