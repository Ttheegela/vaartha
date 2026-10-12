export function PageHeading({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  const words = title.split(" "); const last = words.pop()
  return <div className="mb-10 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="eyebrow mb-3">VĀRTĀ OVERVIEW</p><h1 className="serif-display text-balance text-4xl lg:text-5xl">{words.join(" ")} <em>{last}</em></h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></div>{action}</div>
}
