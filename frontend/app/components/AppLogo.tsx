import Link from "next/link";
import Image from "next/image";

export function AppLogo() {
  return (
    <Link className="app-logo" href="/" aria-label="worktrace 대시보드로 이동">
      <span className="app-logo-mark" aria-hidden="true">
        <Image src="/brand/worktrace-mark.svg" width={34} height={34} alt="" unoptimized />
      </span>
      <span className="app-logo-text">
        <strong>worktrace</strong>
      </span>
    </Link>
  );
}
