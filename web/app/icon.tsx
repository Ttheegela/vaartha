import { markImage } from "./vaa-mark"

const PWA_SIZES = [192, 512]

export const contentType = "image/png"

/** PNG icons for the web app manifest (the browser favicon stays icon.svg). */
export function generateImageMetadata() {
  return PWA_SIZES.map((s) => ({ id: String(s), size: { width: s, height: s }, contentType: "image/png" }))
}

export default async function Icon({ id }: { id: Promise<string> }) {
  const s = Number(await id)
  return markImage(s, Math.round(s * 0.28))
}
