"use client";

export function LogoutButton() {
  async function handleLogout() {
    await fetch("/api/admin/auth", { method: "DELETE" });
    window.location.href = "/admin/login";
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      className="text-xs text-muted-foreground hover:text-foreground"
    >
      Logout
    </button>
  );
}

