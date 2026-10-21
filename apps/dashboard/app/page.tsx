import { redirect } from "next/navigation";

export default function Home() {
  // S01: belum ada sesi → arahkan ke login. Sesungguhnya: cek /me dulu (S02).
  redirect("/login");
}
