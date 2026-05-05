export function formatBoardProbability(
  percent: number | null | undefined,
  digits = 3,
): string {
  if (percent === null || percent === undefined || !Number.isFinite(percent)) return "—";
  return `${percent.toFixed(digits)}%`;
}

export function formatModelProbability(
  probability: number | null | undefined,
  digits = 3,
): string {
  if (probability === null || probability === undefined || !Number.isFinite(probability)) {
    return "—";
  }
  return formatBoardProbability(probability * 100, digits);
}
