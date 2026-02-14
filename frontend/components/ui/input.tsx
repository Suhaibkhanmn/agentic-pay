import { cn } from "@/lib/utils";
import { forwardRef, type InputHTMLAttributes } from "react";

const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "flex w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm",
      "placeholder:text-neutral-400",
      "focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent",
      "disabled:cursor-not-allowed disabled:opacity-40",
      "transition-shadow duration-150",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
