import { markImage } from "./vaa-mark"

const APPLE_ICON_SIZE = 180

export const size = { width: APPLE_ICON_SIZE, height: APPLE_ICON_SIZE }
export const contentType = "image/png"

/** Home-screen icon; iOS rounds the corners itself, so it is full-bleed. */
export default async function AppleIcon() {
  return await markImage(APPLE_ICON_SIZE)
}
