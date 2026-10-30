import clsx from "clsx";
import type { ElementType, ReactNode } from "react";

/**
 * Section entrance, in CSS only (see .rise in globals.css): the part rises and fades as it
 * scrolls into view. There is no hidden starting state held by script, so nothing can get
 * stuck invisible, and browsers without scroll timelines simply show the content.
 */
export function Rise({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: ElementType;
}) {
  return <Tag className={clsx("rise", className)}>{children}</Tag>;
}
