import { cn } from "@/lib/utils"

type LogoProps = {
  variant?: "full" | "mark"
  className?: string
}

export function Logo({ variant = "full", className }: LogoProps) {
  if (variant === "mark") {
    return (
      <span
        aria-label="Vārtā"
        className={cn(
          "serif-display inline-flex size-8 items-center justify-center rounded-[9px] border border-white/[0.08] bg-[#141414] text-[19px] leading-none tracking-[-0.01em] text-[#f5f5f5]",
          className,
        )}
      >
        V<em>ā</em>
      </span>
    )
  }

  return (
    <span
      aria-label="Vārtā"
      className={cn("serif-display text-[28px] leading-none tracking-[-0.01em] text-[#f5f5f5]", className)}
    >
      Vār<em>tā</em>
    </span>
  )
}
