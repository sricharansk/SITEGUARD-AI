// 5x5 risk matrix from GET /risk/matrix. Each cell prints its band and score as text; the current assessment
// is marked with a thick outline and the word "Current", so nothing relies on color alone.
import type { RiskBand, RiskMatrix as Matrix } from "@/lib/types";

const CELL: Record<RiskBand, string> = {
  LOW: "bg-emerald-100 text-emerald-950",
  MEDIUM: "bg-amber-100 text-amber-950",
  HIGH: "bg-orange-200 text-orange-950",
  CRITICAL: "bg-red-300 text-red-950",
};

export interface Cell {
  likelihood: number;
  consequence: number;
}

export function bandFor(matrix: Matrix, likelihood: number, consequence: number): RiskBand | undefined {
  return matrix.bands[likelihood - 1]?.[consequence - 1];
}

export function RiskMatrix({
  matrix,
  current,
  selected,
  onSelect,
}: {
  matrix: Matrix;
  current?: Cell | null;
  selected?: Cell | null;
  onSelect?: (cell: Cell) => void;
}) {
  const levels = [1, 2, 3, 4, 5];
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5 text-xs">
        <caption className="mb-1 text-left text-xs text-slate-600">
          Risk matrix {matrix.version}: score = likelihood × consequence (LOW ≤ 4, MEDIUM ≤ 9, HIGH ≤ 16, CRITICAL ≥ 17).
        </caption>
        <thead>
          <tr>
            <th scope="col" className="px-1 text-left align-bottom font-semibold text-slate-600">
              Likelihood ↓ / Consequence →
            </th>
            {levels.map((c) => (
              <th key={c} scope="col" className="w-16 px-1 text-center align-bottom font-semibold text-slate-700">
                {c}
                <span className="block font-normal text-slate-500">{matrix.consequence[String(c)]}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...levels].reverse().map((l) => (
            <tr key={l}>
              <th scope="row" className="pr-2 text-right font-semibold whitespace-nowrap text-slate-700">
                {l} <span className="font-normal text-slate-500">{matrix.likelihood[String(l)]}</span>
              </th>
              {levels.map((c) => {
                const band = bandFor(matrix, l, c) ?? "LOW";
                const isCurrent = current?.likelihood === l && current?.consequence === c;
                const isSelected = selected?.likelihood === l && selected?.consequence === c;
                const description = `Likelihood ${l} (${matrix.likelihood[String(l)]}), consequence ${c} (${matrix.consequence[String(c)]}): score ${l * c}, ${band}${isCurrent ? ", current assessment" : ""}`;
                const content = (
                  <>
                    <span className="block font-bold">{band}</span>
                    <span className="block tabular-nums">{l * c}</span>
                    {isCurrent ? <span className="block text-[10px] font-bold uppercase">◆ Current</span> : null}
                    {isSelected && !isCurrent ? <span className="block text-[10px] font-bold uppercase">Selected</span> : null}
                  </>
                );
                const ring = isCurrent
                  ? "outline-3 -outline-offset-3 outline-slate-900"
                  : isSelected
                    ? "outline-2 -outline-offset-2 outline-dashed outline-slate-900"
                    : "";
                return (
                  <td
                    key={c}
                    className={`h-14 w-16 rounded-sm p-0 text-center ${CELL[band]} ${ring}`}
                    aria-current={isCurrent ? "true" : undefined}
                    title={description}
                  >
                    {onSelect ? (
                      <button
                        type="button"
                        className="h-full w-full cursor-pointer rounded-sm px-1 hover:bg-white/40"
                        aria-label={`${description}. Use for my assessment`}
                        aria-pressed={isSelected}
                        onClick={() => onSelect({ likelihood: l, consequence: c })}
                      >
                        {content}
                      </button>
                    ) : (
                      <span className="block px-1">
                        <span className="sr-only">{description}</span>
                        <span aria-hidden="true">{content}</span>
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
