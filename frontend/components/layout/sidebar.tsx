"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  CreditCard,
  Building2,
  Shield,
  CheckCircle,
  ScrollText,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/payments", label: "Payments", icon: CreditCard },
  { href: "/vendors", label: "Vendors", icon: Building2 },
  { href: "/policies", label: "Policies", icon: Shield },
  { href: "/approvals", label: "Approvals", icon: CheckCircle },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-neutral-200 bg-white">
      {/* Brand — AP monogram */}
      <div className="px-5 py-5">
        <span className="text-xl font-bold tracking-tighter text-neutral-900 select-none">
          <span>A</span><span className="-ml-[3px]">P</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {navItems.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User / Logout */}
      <div className="border-t border-neutral-100 px-4 py-4">
        <div className="mb-1 text-xs text-neutral-500 truncate">
          {user?.email}
        </div>
        <div className="mb-3 text-[11px] text-neutral-400">
          {user?.role}
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
