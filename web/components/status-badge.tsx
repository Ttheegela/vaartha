import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export function StatusBadge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "positive" | "negative" | "warning" | "neutral" }) {
  return <Badge variant="outline" className={cn("font-mono text-[10px] font-normal", tone === "positive" && "border-primary/30 bg-primary/10 text-primary", tone === "negative" && "border-destructive/30 bg-destructive/10 text-destructive", tone === "warning" && "border-warning/30 bg-warning/10 text-warning", tone === "neutral" && "bg-secondary text-muted-foreground")}>{children}</Badge>
}
