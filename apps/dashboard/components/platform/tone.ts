/** Warna status tenant di konsol platform (teks tetap tampil, bukan warna saja). */
export const STATE_TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  ACTIVE: "success", TRIAL: "warning", RESTRICTED: "warning", SUSPENDED: "danger", TERMINATED: "danger",
};
