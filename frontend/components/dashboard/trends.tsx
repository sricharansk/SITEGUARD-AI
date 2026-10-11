// Response and closure trends (GET /dashboard `trends`). Each period groups the incidents that occurred in it; three
// single-series charts (one scale each, never a dual axis) and the exact table they are drawn from.
import { formatDays, formatHours, periodLabel } from "@/lib/dashboard";
import type { Dashboard } from "@/lib/types";
import { ColumnChart, type ColumnItem } from "../charts";

type Trends = Dashboard["trends"];

function items(trends: Trends, pick: (b: Trends["buckets"][number]) => number | null): ColumnItem[] {
  return trends.buckets.map((b) => ({
    key: b.period,
    label: periodLabel(b.period, true),
    text: periodLabel(b.period),
    value: pick(b),
  }));
}

export function TrendCharts({ trends }: { trends: Trends }) {
  const unit = trends.interval === "week" ? "week" : "month";
  if (trends.buckets.length === 0) {
    return <p className="text-slate-600">No incidents in this period, so there is no trend to show.</p>;
  }
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="min-w-0">
          <h3 className="kicker mb-1">Incidents per {unit}</h3>
          <ColumnChart caption={`Incidents per ${unit} (date occurred)`} items={items(trends, (b) => b.incidents)} />
        </div>
        <div className="min-w-0">
          <h3 className="kicker mb-1">Median time to first response</h3>
          <ColumnChart
            caption={`Median hours from report to first response, per ${unit}`}
            items={items(trends, (b) => b.median_response_hours)}
            format={formatHours}
            emptyText="No incident in this period has had a response yet."
          />
        </div>
        <div className="min-w-0">
          <h3 className="kicker mb-1">Mean days to close</h3>
          <ColumnChart
            caption={`Mean days from report to closure, per ${unit}`}
            items={items(trends, (b) => b.mean_days_to_close)}
            format={(d) => d.toFixed(1)}
            emptyText="No incident in this period has been closed yet."
          />
        </div>
      </div>
      <details className="rounded border border-slate-200">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Trend table ({trends.buckets.length} periods)</summary>
        <div className="overflow-x-auto">
          <table className="table">
            <caption className="sr-only">Response and closure by {unit} of occurrence</caption>
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col">Incidents</th>
                <th scope="col">Closed</th>
                <th scope="col">Still open</th>
                <th scope="col">Responded</th>
                <th scope="col">Median first response</th>
                <th scope="col">Median days to close</th>
                <th scope="col">Mean days to close</th>
              </tr>
            </thead>
            <tbody>
              {trends.buckets.map((b) => (
                <tr key={b.period}>
                  <th scope="row" className="text-left font-medium whitespace-nowrap">
                    {periodLabel(b.period)}
                  </th>
                  <td className="tabular-nums">{b.incidents}</td>
                  <td className="tabular-nums">{b.closed}</td>
                  <td className="tabular-nums">{b.open}</td>
                  <td className="tabular-nums">{b.responded}</td>
                  <td className="tabular-nums whitespace-nowrap">{formatHours(b.median_response_hours)}</td>
                  <td className="tabular-nums whitespace-nowrap">{formatDays(b.median_days_to_close)}</td>
                  <td className="tabular-nums whitespace-nowrap">{formatDays(b.mean_days_to_close)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
